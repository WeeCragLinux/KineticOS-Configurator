"""Clone, select, and update the user's writable image project."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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

from . import project


REPOSITORY_URL = "https://github.com/WeeCragLinux/kinetic-image-builder.git"
PROJECT_DIRECTORY = "kinetic-image-builder"
CONFIG_ROOT = Path(
    os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
) / "kineticos-image-builder"
SETTINGS_FILE = CONFIG_ROOT / "settings.json"


@dataclass
class ProjectChoices:
    base_image: str | None
    modules: dict[str, bool]
    apps: dict[str, dict[str, bool]]
    list_entries: dict[str, dict[tuple[str, str], bool]]


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
    remote = git_output(
        ["git", "-C", str(path), "config", "--get", "remote.origin.url"]
    )
    if remote.returncode != 0:
        config_file = path / ".git" / "config"
        if not config_file.is_file():
            return False
        remote = git_output(
            ["git", "config", "--file", str(config_file), "--get", "remote.origin.url"]
        )
    return (
        remote.returncode == 0
        and normalized_remote(remote.stdout) == normalized_remote(REPOSITORY_URL)
    )


def capture_project_choices(root: Path) -> ProjectChoices:
    """Read current image choices without consulting the checkout's Git database."""
    profile = project.Profile(root)
    module_choices: dict[str, bool] = dict(profile.entries)
    app_choices: dict[str, dict[str, bool]] = {}
    list_choices: dict[str, dict[tuple[str, str], bool]] = {}

    for name, module in project.load_modules(root).items():
        app_choices[name] = {app.name: app.enabled for app in module.apps}
        entries: dict[tuple[str, str], bool] = {}
        for _, section, item in project.iter_items(module.lines):
            if section == "scripts":
                continue
            entries[(section, item.group(3))] = item.group(2) is None
        list_choices[name] = entries

    return ProjectChoices(profile.base_image, module_choices, app_choices, list_choices)


def reapply_project_choices(root: Path, choices: ProjectChoices) -> None:
    """Reapply saved module/app states to matching entries in a fresh template."""
    profile = project.Profile(root)
    base_image = choices.base_image or profile.base_image
    if base_image is None:
        raise ValueError("Neither the saved project nor the upstream profile has a base image.")

    module_entries = [
        (name, choices.modules.get(name, enabled))
        for name, enabled in profile.entries
    ]
    profile.save(base_image, module_entries)

    for module_name, module in project.load_modules(root).items():
        saved_apps = choices.apps.get(module_name, {})
        saved_entries = choices.list_entries.get(module_name, {})
        lines = list(module.lines)
        for _, section, item in project.iter_items(lines):
            name = item.group(3)
            if section == "scripts":
                continue
            enabled = (
                saved_apps.get(name)
                if section in project.APP_SECTIONS
                else saved_entries.get((section, name))
            )
            if enabled is not None:
                project.set_item(lines, section, name, enabled)
        if lines != module.lines:
            module.path.write_text("\n".join(lines) + "\n")


def backup_path(checkout: Path, operation: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = checkout.with_name(f"{checkout.name}.{operation}-backup-{timestamp}")
    suffix = 1
    while backup.exists():
        backup = checkout.with_name(
            f"{checkout.name}.{operation}-backup-{timestamp}-{suffix}"
        )
        suffix += 1
    return backup


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

        try:
            choices = capture_project_choices(self.path)
        except (OSError, ValueError, StopIteration) as error:
            self.completed.emit(False, str(error), "")
            return

        self.replace_with_fresh_clone("update", choices)

    def reset(self) -> None:
        """Replace the checkout with a clean upstream clone without local choices."""
        self.replace_with_fresh_clone("reset")

    def replace_with_fresh_clone(
        self, operation: str, choices: ProjectChoices | None = None
    ) -> None:
        if not is_our_checkout(self.path):
            self.completed.emit(
                False,
                "This project is not a clone of the expected image-builder repository. "
                "No changes were made.",
                "",
            )
            return

        checkout = self.path.expanduser().resolve()
        if not checkout.is_dir():
            self.completed.emit(
                False,
                f"The selected project folder no longer exists:\n{checkout}",
                "",
            )
            return

        try:
            with tempfile.TemporaryDirectory(
                prefix=f".{checkout.name}.{operation}-", dir=checkout.parent
            ) as temporary_directory:
                staged = Path(temporary_directory) / checkout.name
                cloned = git_output(
                    ["git", "clone", "--progress", REPOSITORY_URL, str(staged)]
                )
                if cloned.returncode != 0:
                    self.completed.emit(
                        False,
                        command_output(cloned) or "Could not clone a fresh image project.",
                        "",
                    )
                    return
                if not is_our_checkout(staged):
                    self.completed.emit(
                        False,
                        "The downloaded folder is not a valid clone of the expected repository. "
                        "The selected project was left untouched.",
                        "",
                    )
                    return

                if choices is not None:
                    reapply_project_choices(staged, choices)

                backup = backup_path(checkout, operation)
                os.replace(checkout, backup)
                try:
                    os.replace(staged, checkout)
                except OSError as install_error:
                    try:
                        os.replace(backup, checkout)
                    except OSError as restore_error:
                        raise RuntimeError(
                            f"Could not install the fresh clone ({install_error}). "
                            f"The previous project remains at {backup}; automatic restore "
                            f"also failed ({restore_error})."
                        ) from restore_error
                    raise RuntimeError(
                        f"Could not install the fresh clone ({install_error}); the previous "
                        "project was restored."
                    ) from install_error
        except (OSError, RuntimeError, ValueError, StopIteration) as error:
            self.completed.emit(False, str(error), "")
            return

        detail = (
            "The project was updated from a fresh upstream clone. Existing base-image, "
            "module, app, and list-item choices were reapplied where matching entries remain. "
            "New entries use upstream defaults.\n\n"
            if operation == "update"
            else "The project was reset to a fresh upstream clone.\n\n"
        )
        self.completed.emit(
            True,
            detail + f"The previous folder was saved at:\n{backup}",
            str(checkout),
        )


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

            update_button = QPushButton("Update full template, keep my choices…", body)
            update_button.clicked.connect(self.confirm_update)
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
                f"Replacing the project with a fresh upstream clone:\n{path}"
                if operation in {"reset", "update"}
                else f"Running project operation in:\n{path}"
            )
        )
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle(
            "Cloning project…"
            if operation == "clone"
            else (
                "Resetting project…"
                if operation == "reset"
                else "Updating project…"
            )
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
        if operation in {"reset", "update"}:
            title = "Project reset" if operation == "reset" else "Project updated"
            QMessageBox.information(self, title, detail)
        self.finish_with(Path(checkout))

    def confirm_update(self) -> None:
        if self.saved is None:
            return
        answer = QMessageBox.warning(
            self,
            "Update the full project template?",
            "This replaces the selected project with a fresh upstream clone. The current base "
            "image, module, app, and list-item choices will be reapplied where those entries "
            "still exist. Manual edits to scripts and other files will be replaced.\n\n"
            "A complete backup of the current folder will be created beside it first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_git("update", self.saved)

    def confirm_reset(self) -> None:
        if self.saved is None:
            return
        answer = QMessageBox.warning(
            self,
            "Reset project to a fresh template?",
            "This replaces the selected project with a fresh upstream clone and discards all "
            "current choices and local edits. A complete backup of the current folder will be "
            "created beside it first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_git("reset", self.saved)
