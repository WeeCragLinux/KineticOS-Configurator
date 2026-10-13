"""The main window: standard header bar, title bar modes and the wizard flow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMenu,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..branding import DISPLAY_NAME, PROJECT_URL, VERSION
from ..core import project
from ..core.settings import Settings
from .buildconsole import BuildConsole
from .headerbar import HeaderBar
from .helpwindow import HelpWindow
from .icons import icon_pixmap
from .notices import ROUTINE_MS, NoticeOverlay
from .pages import BasePage, ModulePage, OptionalPage, ReviewPage
from .themewatcher import ThemeWatcher

BASE_DESCRIPTIONS = {
    "ghcr.io/theblack-don/kineticos:default": "AMD and Intel GPUs",
    "ghcr.io/theblack-don/kineticos:nvidia": (
        "NVIDIA GPUs based on Turing or newer: GTX 16 series, and RTX 20, 30, 40 and 50 series"
    ),
    "ghcr.io/theblack-don/kineticos:nvidia-legacy": "NVIDIA GPUs older than the 10 series",
    "ghcr.io/theblack-don/kineticos:deck": "Very early; not recommended for normal use.",
}

ABOUT_COMMENTS = (
    "Clone, configure, update, reset, and build a KineticOS image project.\n\n"
    "Built with Qt 6."
)


class MainWindow(QWidget):
    """One standard window containing the configuration wizard."""

    replace_requested = Signal(object)

    def __init__(
        self,
        root: Path,
        settings: Settings,
        theme: ThemeWatcher,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.root = root
        self.settings = settings
        self.theme = theme
        self.base_descriptions = BASE_DESCRIPTIONS
        self.profile = project.Profile(root)
        self.modules = project.load_modules(root)
        self.profile.ensure_modules(self.modules)
        self.state = project.Selection(
            base_image=self.profile.base_image,
            apps={
                name: {app.name for app in module.apps if app.enabled}
                for name, module in self.modules.items()
                if name != "base" and any(app.enabled for app in module.apps)
            },
            app_modules={
                name
                for name, module in self.modules.items()
                if name != "base" and module.apps
            },
            removal_apps={
                name: {app.name for app in module.apps if app.section == "remove"}
                for name, module in self.modules.items()
                if any(app.section == "remove" for app in module.apps)
            },
            brave_repo_enabled=project.repo_command_enabled(
                self.modules.get("browsers"), "brave"
            ),
            vivaldi_repo_enabled=project.repo_command_enabled(
                self.modules.get("browsers"), "vivaldi"
            ),
        )
        self._help_window: HelpWindow | None = None
        self._last_key_was_alt = False

        self.setWindowTitle(DISPLAY_NAME)
        self.resize(820, 640)
        self.setMinimumSize(560, 440)

        self._build_actions()
        self._build_layout()
        self._build_menu()

        self._install_shortcuts()
        self._apply_title_bar_mode(self.settings.system_title_bar, initial=True)

        self._go(0)

    # -- construction ----------------------------------------------------

    def _build_actions(self) -> None:
        self.action_back = QAction("Back", self)
        self.action_back.setToolTip("Return to the previous step")
        self.action_back.triggered.connect(self._back)

        self.action_next = QAction("Next", self)
        self.action_next.triggered.connect(self._primary_triggered)

        self.action_system_title_bar = QAction("Use System Title Bar", self)
        self.action_system_title_bar.setCheckable(True)
        self.action_system_title_bar.setChecked(self.settings.system_title_bar)
        self.action_system_title_bar.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.action_system_title_bar.setToolTip(
            "Use the compositor's title bar (Ctrl+Shift+M)"
        )
        self.action_system_title_bar.toggled.connect(self._apply_title_bar_mode)

        self.action_open_project = QAction("Open project…", self)
        self.action_open_project.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open_project.triggered.connect(self._open_project)

        self.action_help = QAction("Help", self)
        self.action_help.setShortcut(QKeySequence("F1"))
        self.action_help.triggered.connect(self._show_help)

        self.action_about = QAction(f"About {DISPLAY_NAME}", self)
        self.action_about.triggered.connect(self._show_about)

        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self.close)

        for action in (
            self.action_back,
            self.action_system_title_bar,
            self.action_open_project,
            self.action_help,
            self.action_about,
            self.action_quit,
        ):
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self.addAction(action)

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderBar(self)
        self.header.add_start_action(self.action_back)
        self.header.set_primary_action(self.action_next)
        outer.addWidget(self.header)

        self.body = QWidget(self)
        self.body.setProperty("kc", "window")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.body, 1)

        self.stack = QStackedWidget(self.body)
        body_layout.addWidget(self.stack)

        self.base_page = BasePage(self)
        self.stack.addWidget(self.base_page)
        self.module_pages: list[ModulePage] = []
        for name, _ in self.profile.entries:
            module = self.modules.get(name)
            if name == "base" or module is None or not module.apps:
                continue
            page = ModulePage(self, module)
            self.stack.addWidget(page)
            self.module_pages.append(page)
        self.optional_page = OptionalPage(self)
        self.stack.addWidget(self.optional_page)
        self.review_page = ReviewPage(self)
        self.stack.addWidget(self.review_page)

        self.notices = NoticeOverlay(self.body)

        self.installEventFilter(self)

    def _build_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(self.action_open_project)
        menu.addSeparator()
        menu.addAction(self.action_system_title_bar)
        menu.addSeparator()
        menu.addAction(self.action_help)
        menu.addAction(self.action_about)
        menu.addSeparator()
        menu.addAction(self.action_quit)
        self.menu = menu
        self.header.set_menu(menu)
        menu.installEventFilter(self)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("F10"), self, self._open_menu)

    # -- wizard flow -----------------------------------------------------

    def flow(self) -> list[QWidget]:
        pages: list[QWidget] = [self.base_page, *self.module_pages]
        if project.questions(self.state):
            pages.append(self.optional_page)
        pages.append(self.review_page)
        return pages

    def _current_index(self) -> int:
        return self.flow().index(self.stack.currentWidget())

    def _go(self, index: int) -> None:
        pages = self.flow()
        index = max(0, min(index, len(pages) - 1))
        page = pages[index]
        self.stack.setCurrentWidget(page)
        page.on_enter()
        if index == len(pages) - 1:
            self.action_next.setText("Write changes")
        else:
            self.action_next.setText("Next")
        self.action_back.setEnabled(index > 0)
        primary = page.primary_input()
        if primary is not None and primary.isEnabled():
            QTimer.singleShot(0, primary.setFocus)

    def _back(self) -> None:
        self._go(self._current_index() - 1)

    def _primary_triggered(self) -> None:
        pages = self.flow()
        index = self._current_index()
        if index < len(pages) - 1:
            self._go(index + 1)
        else:
            self._write_and_build()

    # -- title bar modes -------------------------------------------------

    def _apply_title_bar_mode(self, system: bool, initial: bool = False) -> None:
        if self.action_system_title_bar.isChecked() != system:
            self.action_system_title_bar.setChecked(system)
        was_visible = self.isVisible()
        if system:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
            self.header.set_window_buttons_visible(False)
            self.header.set_draggable(False)
        else:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.header.set_window_buttons_visible(True)
            self.header.set_draggable(True)
        self.settings.set_system_title_bar(system)
        if not initial and was_visible:
            # GTK can only change the title bar while unrealized; re-show to
            # recreate the native window. One flicker is expected.
            self.show()
            QTimer.singleShot(0, self._focus_primary_input)

    def _focus_primary_input(self) -> None:
        page = self.stack.currentWidget()
        primary = page.primary_input() if hasattr(page, "primary_input") else None
        if primary is not None and primary.isEnabled():
            primary.setFocus()

    # -- main menu and Alt ----------------------------------------------

    def _open_menu(self) -> None:
        button = self.header.menu_button
        button.showMenu()

    def _toggle_menu(self) -> None:
        if self.menu.isVisible():
            self.menu.close()
            QTimer.singleShot(0, self._focus_primary_input)
        else:
            self._open_menu()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt signature)
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress:
            self._last_key_was_alt = event.key() == Qt.Key.Key_Alt
        elif event_type == QEvent.Type.KeyRelease:
            if event.key() == Qt.Key.Key_Alt and self._last_key_was_alt:
                self._toggle_menu()
            self._last_key_was_alt = False
        return False

    # -- dialogs ---------------------------------------------------------

    def _show_help(self) -> None:
        if self._help_window is None:
            self._help_window = HelpWindow(self)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    def _show_about(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"About {DISPLAY_NAME}")
        dialog.setIconPixmap(icon_pixmap(64))
        dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setText(f"<b>{DISPLAY_NAME}</b><br>Version {VERSION}")
        dialog.setInformativeText(
            f"{ABOUT_COMMENTS}\n\n"
            f'<a href="{PROJECT_URL}">Project page and issue tracker</a><br>'
            "Authors: WeeCragLinux<br>"
            "Licence: MIT"
        )
        dialog.exec()

    # -- actions ---------------------------------------------------------

    def _open_project(self) -> None:
        from .chooser import ChooserWindow

        chooser = ChooserWindow(self.settings, self)
        if chooser.exec() == chooser.DialogCode.Accepted and chooser.checkout:
            self.replace_requested.emit(chooser.checkout)

    def _notice(
        self, text: str, timeout_ms: int | None = ROUTINE_MS, status: str | None = None
    ) -> None:
        self.notices.show_message(text, timeout_ms, status)

    # -- apply and build -------------------------------------------------

    def _write_and_build(self) -> None:
        try:
            project.apply(self.root, self.state, self.modules, self.profile)
        except OSError as error:
            QMessageBox.critical(self, "Could not write files", str(error))
            return
        ok, output = project.generate(self.root)
        if not ok:
            QMessageBox.warning(
                self,
                "Files written, but dcli-bootc gen failed",
                output or "dcli-bootc gen failed.",
            )
            return
        self._notice("Files written and dcli-bootc gen completed.", ROUTINE_MS, "positive")

        answer = QMessageBox.question(
            self,
            "Build image now?",
            "Would you like to run dcli-bootc build for this project now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        console = BuildConsole(
            "Building KineticOS image",
            ["dcli-bootc", "build", "-p", str(self.root), "--no-switch"],
            self,
        )
        if not console.run():
            QMessageBox.warning(
                self,
                "Image build failed",
                "dcli-bootc build did not complete successfully.\n\n"
                + console.output.toPlainText()[-4000:],
            )
            return

        switch = QMessageBox.question(
            self,
            "Switch to the new image and reboot?",
            "The image built successfully. Switch this computer to the new image and "
            "reboot now?\n\nThe current deployment should remain available for rollback.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if switch != QMessageBox.StandardButton.Yes:
            return

        switching = BuildConsole(
            "Switching to the new image",
            ["dcli-bootc", "switch", "-p", str(self.root), "--force", "--reboot"],
            self,
        )
        if not switching.run():
            QMessageBox.warning(
                self,
                "Could not switch image",
                "dcli-bootc switch did not complete successfully. Check its output and "
                "your system's bootc permissions.\n\n"
                + switching.output.toPlainText()[-4000:],
            )
        else:
            self._notice("Switching to the new image.", None, "neutral")
