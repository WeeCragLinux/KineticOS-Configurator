"""The shared header bar: logo, actions and the main menu.

The same instance is kept for both title bar modes; only the window buttons and
whether the window is frameless change.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from ..branding import WORDMARK
from .icons import icon_pixmap


class HeaderBar(QFrame):
    """App title bar contents, packed like the standard's header bar."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setProperty("kc", "headerbar")
        self._window = window
        self._draggable = False
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        logo = QHBoxLayout()
        logo.setSpacing(10)
        icon = QLabel(self)
        pixmap = icon_pixmap(28)
        if not pixmap.isNull():
            icon.setPixmap(pixmap)
        icon.setFixedWidth(28)
        wordmark = QLabel(WORDMARK, self)
        wordmark.setProperty("kc", "wordmark")
        logo.addWidget(icon)
        logo.addWidget(wordmark)
        layout.addLayout(logo)

        self._start = QHBoxLayout()
        self._start.setSpacing(8)
        layout.addLayout(self._start)

        layout.addStretch(1)

        self.primary_button = QPushButton(self)
        self.primary_button.setProperty("kc", "primary")
        self.primary_button.hide()
        layout.addWidget(self.primary_button)

        self.menu_button = QToolButton(self)
        self.menu_button.setToolTip("Main menu")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setAutoRaise(True)
        menu_icon = QIcon.fromTheme("open-menu-symbolic")
        if menu_icon.isNull():
            self.menu_button.setText("\u2630")  # ☰
            font = self.menu_button.font()
            font.setPointSizeF(font.pointSizeF() + 4)
            self.menu_button.setFont(font)
        else:
            self.menu_button.setIcon(menu_icon)
        layout.addWidget(self.menu_button)

        self._window_buttons = self._build_window_buttons()
        layout.addWidget(self._window_buttons)

        self.setFixedHeight(46)

    # -- contents -------------------------------------------------------

    def set_menu(self, menu: QMenu) -> None:
        self.menu_button.setMenu(menu)

    def add_start_action(self, action: QAction) -> QPushButton:
        button = QPushButton(action.text())
        button.setDefault(False)
        button.setAutoDefault(False)
        action.changed.connect(lambda: self._sync_button(button, action))
        button.clicked.connect(action.trigger)
        self._sync_button(button, action)
        self._start.addWidget(button)
        return button

    def set_primary_action(self, action: QAction | None) -> None:
        if action is None:
            self.primary_button.hide()
            return
        if getattr(self, "_primary_action", None) is not action:
            self.primary_button.clicked.connect(action.trigger)
            action.changed.connect(lambda: self._sync_primary(action))
            self._primary_action = action
        self._sync_primary(action)

    def _sync_primary(self, action: QAction) -> None:
        self.primary_button.setText(action.text())
        self.primary_button.setToolTip(action.toolTip())
        self.primary_button.setEnabled(action.isEnabled())
        self.primary_button.setVisible(True)

    def _sync_button(self, button: QPushButton, action: QAction) -> None:
        button.setText(action.text())
        button.setEnabled(action.isEnabled())
        button.setVisible(action.isVisible())
        button.setToolTip(action.toolTip())

    def _build_window_buttons(self) -> QWidget:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        style = self.style()
        self.minimize_button = self._button(style, QStyle.StandardPixmap.SP_TitleBarMinButton)
        self.maximize_button = self._button(style, QStyle.StandardPixmap.SP_TitleBarMaxButton)
        self.close_button = self._button(style, QStyle.StandardPixmap.SP_TitleBarCloseButton)
        self.minimize_button.clicked.connect(self._window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximize)
        self.close_button.clicked.connect(self._window.close)
        row.addWidget(self.minimize_button)
        row.addWidget(self.maximize_button)
        row.addWidget(self.close_button)
        return container

    @staticmethod
    def _button(style, pixmap) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)
        button.setIcon(style.standardIcon(pixmap))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return button

    # -- title bar modes -------------------------------------------------

    def set_window_buttons_visible(self, visible: bool) -> None:
        self._window_buttons.setVisible(visible)

    def set_draggable(self, draggable: bool) -> None:
        self._draggable = draggable

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # -- dragging when frameless ----------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        child = self.childAt(event.position().toPoint())
        if (
            self._draggable
            and event.button() == Qt.MouseButton.LeftButton
            and not isinstance(child, QAbstractButton)
        ):
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self._window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self._draggable and event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
