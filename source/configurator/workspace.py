"""Clone, select, and update the user's writable image project."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QDialog,
    QWidget,
)

from .template_sync import merge_project_entries


REPOSITORY_URL = "https://github.com/WeeCragLinux/kinetic-image-builder.git"
PROJECT_DIRECTORY = "kinetic-image-builder"
TEMPLATE_BASE_REF = "refs/kineticos-image-builder/template-base"
CONFIG_ROOT = Path(
    os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
) / "kineticos-image-builder"
SETTINGS_FILE = CONFIG_ROOT / "settings.json"


def normalized_remote(url: str) -> str:
    return url.strip().rstrip("/").removesuffix(".git").rstrip("/").lower()


def is_project(path: Path) -> bool:
    return (path / "profile.yaml").is_file() and (path / "modules").is_dir()


def command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )


def git_output(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def is_our_checkout(path: Path) -> bool:
    if not is_project(path):
        return False
    remote = git_output(["git", "-C", str(path), "remote", "get-url", "origin"])
    return (
        remote.returncode == 0
        and normalized_remote(remote.stdout) == normalized_remote(REPOSITORY_URL)
    )


def saved_checkout() -> Path | None:
    try:
        settings = json.loads(SETTINGS_FILE.read_text())
        checkout = Path(settings["checkout_path"]).expanduser()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return checkout if is_project(checkout) else None


def save_checkout(checkout: Path) -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps({"checkout_path": str(checkout.resolve())}, indent=2) + "\n"
    )
    temp_file.replace(SETTINGS_FILE)


class GitWorker(QThread):
    completed = Signal(bool, str, str)

    def __init__(self, operation: str, path: Path):
        super().__init__()
        self.operation = operation
        self.path = path

    def run(self) -> None:
        if shutil.which("git") is None:
            self.completed.emit(False, "Git is not installed or is not on PATH.", "")
            return
        try:
            if self.operation == "clone":
                self.clone()
            elif self.operation == "reset":
                self.reset()
            else:
                self.update()
        except OSError as error:
            self.completed.emit(False, str(error), "")

    def clone(self) -> None:
        if self.path.exists():
            if is_project(self.path):
                self.completed.emit(True, "Opened the existing image project.", str(self.path))
            else:
                self.completed.emit(
                    False,
                    f"The destination already exists and is not an image project:\n{self.path}\n\n"
                    "Choose another folder or open the existing project directly.",
                    "",
                )
            return

        result = git_output(["git", "clone", "--progress", REPOSITORY_URL, str(self.path)])
        if result.returncode == 0 and is_project(self.path):
            self.completed.emit(True, "Image project cloned successfully.", str(self.path))
        else:
            self.completed.emit(
                False,
                command_output(result) or "Git clone failed or the downloaded project is incomplete.",
                "",
            )

    def update(self) -> None:
        if not is_our_checkout(self.path):
            self.completed.emit(
                False,
                "This project is not a clone of the expected image-builder repository. "
                "No changes were made.",
                "",
            )
            return

        upstream = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ]
        )
        if upstream.returncode != 0 or not upstream.stdout.strip():
            self.completed.emit(
                False,
                command_output(upstream)
                or "This checkout has no upstream branch configured.",
                "",
            )
            return

        fetched = git_output(["git", "-C", str(self.path), "fetch", "--quiet"])
        if fetched.returncode != 0:
            self.completed.emit(
                False,
                command_output(fetched) or "Could not fetch template updates.",
                "",
            )
            return

        upstream_ref = upstream.stdout.strip()
        target = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "rev-parse",
                "--verify",
                f"{upstream_ref}^{{commit}}",
            ]
        )
        if target.returncode != 0 or not target.stdout.strip():
            self.completed.emit(
                False,
                command_output(target) or "Could not find the fetched template revision.",
                "",
            )
            return
        target_oid = target.stdout.strip()

        saved_base = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "rev-parse",
                "--verify",
                f"{TEMPLATE_BASE_REF}^{{commit}}",
            ]
        )
        base_oid = saved_base.stdout.strip() if saved_base.returncode == 0 else ""
        if not base_oid:
            head = git_output(["git", "-C", str(self.path), "rev-parse", "HEAD"])
            if head.returncode != 0 or not head.stdout.strip():
                self.completed.emit(
                    False,
                    command_output(head) or "Could not determine the current template revision.",
                    "",
                )
                return
            base_oid = head.stdout.strip()

        ancestry = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "merge-base",
                "--is-ancestor",
                base_oid,
                target_oid,
            ]
        )
        if ancestry.returncode != 0:
            self.completed.emit(
                False,
                "The upstream template history has diverged from the last synchronized revision. "
                "No project files were changed.",
                "",
            )
            return

        try:
            base_files = self.template_files(base_oid)
            upstream_files = self.template_files(target_oid)
            summary = merge_project_entries(self.path, base_files, upstream_files)
        except (OSError, RuntimeError, ValueError) as error:
            self.completed.emit(False, str(error), "")
            return

        if saved_base.returncode == 0:
            advanced = git_output(
                [
                    "git",
                    "-C",
                    str(self.path),
                    "update-ref",
                    TEMPLATE_BASE_REF,
                    target_oid,
                    base_oid,
                ]
            )
        else:
            advanced = git_output(
                ["git", "-C", str(self.path), "update-ref", TEMPLATE_BASE_REF, target_oid]
            )
        if advanced.returncode != 0:
            self.completed.emit(
                False,
                "Template entries were synchronized, but the synchronization point could not "
                "be saved. Retry the update.\n\n"
                + (command_output(advanced) or "Git could not update its template reference."),
                "",
            )
            return

        details = []
        if summary.added:
            details.append(
                f"Added {summary.added} new template entr"
                f"{'y' if summary.added == 1 else 'ies'}."
            )
        if summary.removed:
            details.append(
                f"Removed {summary.removed} unchanged entr{'y' if summary.removed == 1 else 'ies'} "
                "that upstream removed."
            )
        if summary.retained:
            details.append(
                f"Kept {summary.retained} locally changed entr"
                f"{'y' if summary.retained == 1 else 'ies'} "
                "that upstream removed."
            )
        if not details:
            details.append("No new or removed template entries were found.")
        details.append(
            "Existing entries, enabled/disabled choices, and other local edits were kept. "
            "This sync does not update other repository files."
        )
        self.completed.emit(True, "\n".join(details), str(self.path))

    def reset(self) -> None:
        """Restore this checkout to the latest origin default-branch clone state."""
        if not is_our_checkout(self.path):
            self.completed.emit(
                False,
                "This project is not a clone of the expected image-builder repository. "
                "No changes were made.",
                "",
            )
            return

        fetched = git_output(["git", "-C", str(self.path), "fetch", "--quiet", "origin"])
        if fetched.returncode != 0:
            self.completed.emit(
                False,
                command_output(fetched) or "Could not fetch the base template.",
                "",
            )
            return

        git_output(["git", "-C", str(self.path), "remote", "set-head", "origin", "--auto"])
        default_ref = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "symbolic-ref",
                "--quiet",
                "refs/remotes/origin/HEAD",
            ]
        )
        if default_ref.returncode == 0 and default_ref.stdout.strip():
            target_ref = default_ref.stdout.strip()
        else:
            upstream = git_output(
                [
                    "git",
                    "-C",
                    str(self.path),
                    "rev-parse",
                    "--abbrev-ref",
                    "--symbolic-full-name",
                    "@{upstream}",
                ]
            )
            if upstream.returncode != 0 or not upstream.stdout.strip():
                self.completed.emit(
                    False,
                    command_output(upstream)
                    or "Could not determine the repository's default branch.",
                    "",
                )
                return
            target_ref = upstream.stdout.strip()

        target = git_output(
            ["git", "-C", str(self.path), "rev-parse", "--verify", f"{target_ref}^{{commit}}"]
        )
        if target.returncode != 0 or not target.stdout.strip():
            self.completed.emit(
                False,
                command_output(target) or "Could not locate the base template revision.",
                "",
            )
            return
        target_oid = target.stdout.strip()

        # Verify the target is a complete project before creating a backup or
        # touching the selected checkout.
        try:
            self.template_files(target_oid)
        except RuntimeError as error:
            self.completed.emit(False, str(error), "")
            return

        checkout = self.path.resolve()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = checkout.with_name(f"{checkout.name}.reset-backup-{timestamp}")
        suffix = 1
        while backup.exists():
            backup = checkout.with_name(
                f"{checkout.name}.reset-backup-{timestamp}-{suffix}"
            )
            suffix += 1
        shutil.copytree(checkout, backup, symlinks=True)

        reset = git_output(["git", "-C", str(checkout), "reset", "--hard", target_oid])
        if reset.returncode != 0:
            self.completed.emit(
                False,
                "Git could not reset the project. A pre-reset backup is available at:\n"
                f"{backup}\n\n{command_output(reset)}",
                "",
            )
            return

        clean = git_output(["git", "-C", str(checkout), "clean", "-ffdx"])
        if clean.returncode != 0:
            self.completed.emit(
                False,
                "The tracked files were reset, but untracked/ignored files could not all be "
                "removed. A pre-reset backup is available at:\n"
                f"{backup}\n\n{command_output(clean)}",
                "",
            )
            return

        advanced = git_output(
            ["git", "-C", str(checkout), "update-ref", TEMPLATE_BASE_REF, target_oid]
        )
        if advanced.returncode != 0:
            self.completed.emit(
                False,
                "The project files were reset, but the template sync reference could not be "
                "updated. A pre-reset backup is available at:\n"
                f"{backup}\n\n{command_output(advanced)}",
                "",
            )
            return

        self.completed.emit(
            True,
            "The project was reset to the latest upstream base template. A complete backup "
            f"of the previous folder was saved at:\n{backup}",
            str(checkout),
        )

    def template_files(self, revision: str) -> dict[str, str]:
        listing = git_output(
            [
                "git",
                "-C",
                str(self.path),
                "ls-tree",
                "-r",
                "--name-only",
                revision,
                "--",
                "modules",
            ]
        )
        if listing.returncode != 0:
            raise RuntimeError(command_output(listing) or "Could not list template modules.")
        files = ["profile.yaml"]
        files.extend(
            name
            for name in listing.stdout.splitlines()
            if name.startswith("modules/") and name.endswith(".yaml")
        )
        result: dict[str, str] = {}
        for name in files:
            content = git_output(
                ["git", "-C", str(self.path), "show", f"{revision}:{name}"]
            )
            if content.returncode != 0:
                raise RuntimeError(
                    command_output(content) or f"Could not read {name} at {revision}."
                )
            result[name] = content.stdout
        return result


class ProjectChooser(QDialog):
    """Choose an existing project or clone one into a user-selected location."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KineticOS Image Configurator")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setFixedSize(640, 420)
        self.checkout: Path | None = None
        self.saved = saved_checkout()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        banner = QFrame(self)
        banner.setObjectName("projectChooserBanner")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(20, 12, 20, 12)
        banner_layout.setSpacing(4)
        title = QLabel("Welcome to KineticOS Image Configurator", banner)
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        description = QLabel(
            "Choose a project to configure, or clone a fresh copy. Projects stay in a "
            "writable folder you control.",
            banner,
        )
        description.setWordWrap(True)
        banner_layout.addWidget(title)
        banner_layout.addWidget(description)
        banner.setStyleSheet(
            "QFrame#projectChooserBanner {"
            " background-color: palette(alternate-base);"
            " border-bottom: 1px solid palette(mid);"
            "}"
            "QFrame#projectChooserBanner QLabel { background: transparent; border: none; }"
        )
        layout.addWidget(banner)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 12)
        body_layout.setSpacing(8)
        layout.addWidget(body, 1)

        if self.saved:
            saved_title = QLabel("Saved project", body)
            saved_title.setStyleSheet("font-size: 16px; font-weight: 700;")
            body_layout.addWidget(saved_title)

            path_label = QLabel(str(self.saved), body)
            path_label.setWordWrap(True)
            body_layout.addWidget(path_label)

            open_button = QPushButton("Open saved project", body)
            open_button.setDefault(True)
            open_button.clicked.connect(lambda: self.finish_with(self.saved))
            body_layout.addWidget(open_button)

            update_button = QPushButton("Sync new/removed entries, then open", body)
            update_button.clicked.connect(lambda: self.run_git("update", self.saved))
            body_layout.addWidget(update_button)

            reset_button = QPushButton("Reset project to a fresh template…", body)
            reset_button.clicked.connect(self.confirm_reset)
            body_layout.addWidget(reset_button)

            separator = QFrame(body)
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            body_layout.addWidget(separator)

        choices = QHBoxLayout()
        choices.setSpacing(8)
        clone_button = QPushButton("Clone image project…", body)
        clone_button.clicked.connect(self.choose_clone)
        choices.addWidget(clone_button)

        open_existing_button = QPushButton("Open an existing project…", body)
        open_existing_button.clicked.connect(self.choose_existing)
        choices.addWidget(open_existing_button)
        body_layout.addLayout(choices)
        body_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_button = QPushButton("Cancel", body)
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        body_layout.addLayout(footer)

        for button in self.findChildren(QPushButton):
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setMinimumHeight(36)

    def finish_with(self, checkout: Path | None) -> None:
        if checkout is None or not is_project(checkout):
            QMessageBox.warning(self, "Project not found", "That folder is not a valid image project.")
            return
        try:
            save_checkout(checkout)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Project ready, location not saved",
                f"The project can be opened, but its location could not be remembered:\n{error}",
            )
        self.checkout = checkout.resolve()
        self.accept()

    def choose_existing(self) -> None:
        initial = str(self.saved or Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Open image project", initial)
        if not selected:
            return
        path = Path(selected).expanduser()
        if not is_project(path):
            QMessageBox.warning(
                self,
                "Not an image project",
                "Choose a folder containing profile.yaml and a modules/ directory.",
            )
            return
        self.finish_with(path)

    def choose_clone(self) -> None:
        if shutil.which("git") is None:
            QMessageBox.critical(self, "Git is required", "Install Git before cloning an image project.")
            return
        initial = Path.home() / "Projects"
        if not initial.is_dir():
            initial = Path.home()
        parent = QFileDialog.getExistingDirectory(
            self, "Choose where to store the image project", str(initial)
        )
        if not parent:
            return
        self.run_git("clone", Path(parent).expanduser() / PROJECT_DIRECTORY)

    def run_git(self, operation: str, path: Path) -> None:
        message = (
            f"Cloning the image project into:\n{path}"
            if operation == "clone"
            else (
                f"Resetting the project to a fresh upstream template:\n{path}"
                if operation == "reset"
                else f"Syncing new and removed template entries in:\n{path}"
            )
        )
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle(
            "Cloning project…"
            if operation == "clone"
            else ("Resetting project…" if operation == "reset" else "Syncing template entries…")
        )
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        outcome: list[tuple[bool, str, str]] = []
        worker = GitWorker(operation, path)

        def completed(success: bool, detail: str, checkout: str) -> None:
            outcome.append((success, detail, checkout))
            progress.accept()

        worker.completed.connect(completed)
        QTimer.singleShot(0, worker.start)
        progress.exec()
        worker.wait()

        if not outcome:
            QMessageBox.warning(self, "Project operation failed", "Git ended without a result.")
            return
        success, detail, checkout = outcome[0]
        if not success:
            QMessageBox.warning(self, "Project operation failed", detail)
            return
        if operation == "reset":
            QMessageBox.information(self, "Project reset", detail)
        self.finish_with(Path(checkout))

    def confirm_reset(self) -> None:
        if self.saved is None:
            return
        answer = QMessageBox.warning(
            self,
            "Reset project to a fresh template?",
            "This replaces the selected project with the latest upstream template and removes "
            "all local edits, untracked files, and ignored build files.\n\n"
            "A complete backup of the current folder will be created beside it first. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_git("reset", self.saved)
