"""Choose an existing project or clone one into a user-selected location."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..branding import DISPLAY_NAME
from ..core import workspace
from ..core.settings import Settings
from . import widgets
from .secondary import SecondaryWindow


class ChooserWindow(SecondaryWindow):
    """The first window: open, clone, update or reset an image project."""

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(DISPLAY_NAME, parent)
        self.setWindowTitle("Choose project")
        self.settings = settings
        self.checkout: Path | None = None
        self.saved = workspace.saved_checkout(settings)
        self.resize(660, 480)

        self.body_layout.addWidget(
            widgets.label(
                "Choose a project to configure, or clone a fresh copy. Projects stay "
                "in a writable folder you control.",
                "muted",
                self.body,
            )
        )

        if self.saved is not None:
            card = widgets.card(parent=self.body)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 14, 14, 14)
            card_layout.setSpacing(8)
            card_layout.addWidget(widgets.section_label("Saved project", card))
            path_label = widgets.label(str(self.saved), "mono", card)
            card_layout.addWidget(path_label)
            self._full_button(card_layout, "Open saved project", self._open_saved, primary=True)
            self._full_button(
                card_layout, "Update full template, keep my choices…", self._confirm_update
            )
            self._full_button(
                card_layout, "Reset project to a fresh template…", self._confirm_reset
            )
            self.body_layout.addWidget(card)

        actions = QHBoxLayout()
        clone = self._full_button(None, "Clone image project…", self._choose_clone)
        existing = self._full_button(None, "Open an existing project…", self._choose_existing)
        actions.addWidget(clone)
        actions.addWidget(existing)
        self.body_layout.addLayout(actions)
        self.body_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("Cancel", self.body)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.body_layout.addLayout(footer)

    def _full_button(self, layout, text, handler, primary: bool = False) -> QPushButton:
        button = QPushButton(text, self.body)
        if primary:
            button.setProperty("kc", "primary")
            button.setDefault(True)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setMinimumHeight(36)
        button.clicked.connect(handler)
        if layout is not None:
            layout.addWidget(button)
        return button

    # -- choices ---------------------------------------------------------

    def _finish_with(self, checkout: Path | None) -> None:
        if checkout is None or not workspace.is_project(checkout):
            QMessageBox.warning(
                self, "Project not found", "That folder is not a valid image project."
            )
            return
        try:
            workspace.save_checkout(checkout, self.settings)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Project ready, location not saved",
                f"The project can be opened, but its location could not be "
                f"remembered:\n{error}",
            )
        self.checkout = checkout.resolve()
        self.accept()

    def _open_saved(self) -> None:
        self._finish_with(self.saved)

    def _choose_existing(self) -> None:
        initial = str(self.saved or Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Open image project", initial)
        if not selected:
            return
        path = Path(selected).expanduser()
        if not workspace.is_project(path):
            QMessageBox.warning(
                self,
                "Not an image project",
                "Choose a folder containing profile.yaml and a modules/ directory.",
            )
            return
        self._finish_with(path)

    def _choose_clone(self) -> None:
        if shutil.which("git") is None:
            QMessageBox.critical(
                self, "Git is required", "Install Git before cloning an image project."
            )
            return
        initial = Path.home() / "Projects"
        if not initial.is_dir():
            initial = Path.home()
        parent = QFileDialog.getExistingDirectory(
            self, "Choose where to store the image project", str(initial)
        )
        if not parent:
            return
        self._run_git("clone", Path(parent).expanduser() / workspace.PROJECT_DIRECTORY)

    def _confirm_update(self) -> None:
        if self.saved is None:
            return
        answer = QMessageBox.warning(
            self,
            "Update the full project template?",
            "This replaces the selected project with a fresh upstream clone. The "
            "current base image, module, app, and list-item choices will be reapplied "
            "where those entries still exist. Manual edits to scripts and other files "
            "will be replaced.\n\nA complete backup of the current folder will be "
            "created beside it first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_git("update", self.saved)

    def _confirm_reset(self) -> None:
        if self.saved is None:
            return
        answer = QMessageBox.warning(
            self,
            "Reset project to a fresh template?",
            "This replaces the selected project with a fresh upstream clone and "
            "discards all current choices and local edits. A complete backup of the "
            "current folder will be created beside it first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_git("reset", self.saved)

    # -- git --------------------------------------------------------------

    def _run_git(self, operation: str, path: Path) -> None:
        message = (
            f"Cloning the image project into:\n{path}"
            if operation == "clone"
            else f"Replacing the project with a fresh upstream clone:\n{path}"
        )
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle(
            "Cloning project…"
            if operation == "clone"
            else ("Resetting project…" if operation == "reset" else "Updating project…")
        )
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        outcome: list[tuple[bool, str, str]] = []
        worker = workspace.GitWorker(operation, path)

        def completed(success: bool, detail: str, checkout: str) -> None:
            outcome.append((success, detail, checkout))
            progress.accept()

        worker.completed.connect(completed)
        QTimer.singleShot(0, worker.start)
        progress.exec()
        worker.wait()

        if not outcome:
            QMessageBox.warning(
                self, "Project operation failed", "Git ended without a result."
            )
            return
        success, detail, checkout = outcome[0]
        if not success:
            QMessageBox.warning(self, "Project operation failed", detail)
            return
        if operation in {"reset", "update"}:
            QMessageBox.information(
                self, "Project reset" if operation == "reset" else "Project updated", detail
            )
        self._finish_with(Path(checkout))
