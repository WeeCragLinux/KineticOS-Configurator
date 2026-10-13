"""Non-blocking notices shown inside the window instead of a dialog.

A notice is a centred label at the bottom of the body, overlaid so it never
blocks clicks. Routine results disappear after 5 s, results the user may want
to read (a saved path) after 10 s, and progress messages stay until the next
notice replaces them.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .widgets import refresh

ROUTINE_MS = 5000
READ_MS = 10000
ANIMATION_MS = 180
MAX_WIDTH = 640


class Notice(QFrame):
    """A single revealed notice; reuse it by calling :meth:`show_message`."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("kc", "notice")
        self.setMaximumWidth(MAX_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self.setMinimumHeight(0)
        self.setMaximumHeight(0)
        self.hide()

        self._animation = QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.finished.connect(self._on_animation_finished)
        self._collapsing = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_message)

    def show_message(
        self,
        text: str,
        timeout_ms: int | None = ROUTINE_MS,
        status: str | None = None,
    ) -> None:
        self._label.setText(text)
        self.setProperty("status", status)
        refresh(self)
        self._collapsing = False
        self.show()
        self.raise_()
        self._animate(self.maximumHeight(), self.sizeHint().height() + 4)
        self._timer.stop()
        if timeout_ms is not None:
            self._timer.start(timeout_ms)

    def hide_message(self) -> None:
        self._timer.stop()
        if not self.isVisible():
            return
        self._collapsing = True
        self._animate(self.maximumHeight(), 0)

    def _animate(self, start: int, end: int) -> None:
        self._animation.stop()
        self._animation.setStartValue(max(0, start))
        self._animation.setEndValue(max(0, end))
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self._collapsing:
            self.hide()
            self.setMaximumHeight(0)


class NoticeOverlay(QWidget):
    """Floats a :class:`Notice` over ``body``, centred near its bottom."""

    def __init__(self, body: QWidget, parent: QWidget | None = None):
        super().__init__(parent or body)
        self._body = body
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 16)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.notice = Notice(self)
        row.addWidget(self.notice)
        row.addStretch(1)
        layout.addLayout(row)

        body.installEventFilter(self)
        self.setGeometry(body.rect())

    def show_message(
        self,
        text: str,
        timeout_ms: int | None = ROUTINE_MS,
        status: str | None = None,
    ) -> None:
        self.raise_()
        self.notice.show_message(text, timeout_ms, status)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt signature)
        if watched is self._body and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._body.rect())
        return False
