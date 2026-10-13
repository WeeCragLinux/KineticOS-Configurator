"""Application lifecycle and entry point.

`startup` sets the application name and icon and installs the stylesheet; the
first `activate` builds the window. The wizard lives in the main window
(`ui/mainwindow.py`).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from .branding import APP_ID, DISPLAY_NAME, SNAPSHOT_ENV
from .core import workspace
from .core.settings import Settings
from .ui.chooser import ChooserWindow
from .ui.icons import app_icon
from .ui.mainwindow import MainWindow
from .ui.themewatcher import ThemeWatcher

SNAPSHOT_DELAY_MS = 3000


def _slug(title: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", title).strip("-") or "window"


def _install_snapshot(app: QApplication, folder: str) -> None:
    destination = Path(folder).expanduser()
    destination.mkdir(parents=True, exist_ok=True)

    def capture() -> None:
        for widget in app.topLevelWidgets():
            if not widget.isVisible():
                continue
            title = widget.windowTitle() or type(widget).__name__
            widget.grab().save(str(destination / f"{_slug(title)}.png"))
        app.quit()

    QTimer.singleShot(SNAPSHOT_DELAY_MS, capture)


def main(root: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setOrganizationName("WeeCragLinux")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())

    settings = Settings()
    theme = ThemeWatcher(app)
    snapshot_folder = os.environ.get(SNAPSHOT_ENV)

    if root is None:
        chooser = ChooserWindow(settings)
        if snapshot_folder:
            # In snapshot mode show the chooser without blocking so it can be
            # captured, then let the snapshot timer quit the application.
            chooser.show()
            _install_snapshot(app, snapshot_folder)
            return app.exec()
        if chooser.exec() != QDialog.DialogCode.Accepted or chooser.checkout is None:
            return 0
        root = chooser.checkout
    elif not workspace.is_project(root):
        QMessageBox.critical(
            None,
            "Not an image project",
            f"Choose a folder containing profile.yaml and a modules/ directory.\n\n{root}",
        )
        return 1

    windows: list[MainWindow] = []

    def open_main(path: Path) -> None:
        window = MainWindow(path, settings, theme)
        window.replace_requested.connect(
            lambda new_root: (window.close(), open_main(new_root))
        )
        windows.append(window)
        window.show()

    open_main(Path(root))

    if snapshot_folder:
        _install_snapshot(app, snapshot_folder)

    return app.exec()
