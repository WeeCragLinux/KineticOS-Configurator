"""Clone, select, and update the user's writable image project.

Only the non-widget parts live here (project detection, git operations, choice
capture/reapply and the `GitWorker` thread). The chooser UI is in
`configurator/ui/chooser.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import project
from .settings import Settings


REPOSITORY_URL = "https://github.com/WeeCragLinux/kinetic-image-builder.git"
PROJECT_DIRECTORY = "kinetic-image-builder"


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


def saved_checkout(settings: Settings | None = None) -> Path | None:
    store = settings or Settings()
    checkout = store.checkout_path
    if checkout is None:
        return None
    return checkout if is_project(checkout) else None


def save_checkout(checkout: Path, settings: Settings | None = None) -> None:
    store = settings or Settings()
    store.set_checkout_path(checkout)


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
