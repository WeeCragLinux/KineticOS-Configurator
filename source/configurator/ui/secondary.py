"""Secondary windows (dialogs and help) with the standard's wordmark header."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SecondaryWindow(QDialog):
    """A dialog with a client-side header bar and a wordmark title."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle(title)
        self._drag_offset = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(self)
        header.setProperty("kc", "headerbar")
        header.setFixedHeight(46)
        header.installEventFilter(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 8, 0)
        header_layout.setSpacing(8)
        title_label = QLabel(title.upper(), header)
        title_label.setProperty("kc", "wordmark")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        close_button = QToolButton(header)
        close_button.setAutoRaise(True)
        close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)
        outer.addWidget(header)

        self.body = QWidget(self)
        self.body.setProperty("kc", "dialog-body")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 18, 18, 18)
        self.body_layout.setSpacing(10)
        outer.addWidget(self.body, 1)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt signature)
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return True
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                return True
        elif event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None
        return super().eventFilter(watched, event)
