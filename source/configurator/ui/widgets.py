"""Small helpers for the standard's shared component classes.

Shared component classes are set as Qt dynamic properties (for example
``kc="card"``) and matched from ``assets/style.qss`` with ``[kc="card"]``
selectors. Custom properties are not re-evaluated by Qt automatically, so call
:func:`refresh` after changing one.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QToolButton, QWidget


def refresh(widget: QWidget) -> None:
    """Re-polish a widget so a changed dynamic property takes effect."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def label(text: str = "", role: str | None = None, parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setWordWrap(True)
    if role:
        widget.setProperty("kc", role)
    return widget


def section_label(text: str, parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text.upper(), parent)
    widget.setProperty("kc", "section-label")
    return widget


def card(flush: bool = False, parent: QWidget | None = None) -> QFrame:
    widget = QFrame(parent)
    widget.setProperty("kc", "card")
    if flush:
        widget.setProperty("flush", "true")
        widget.setFrameShape(QFrame.Shape.NoFrame)
    return widget


def button(text: str, role: str | None = None, parent: QWidget | None = None) -> QPushButton:
    widget = QPushButton(text, parent)
    if role:
        widget.setProperty("kc", role)
    return widget


def tool_button(icon=None, tooltip: str = "", parent: QWidget | None = None) -> QToolButton:
    widget = QToolButton(parent)
    if icon is not None:
        widget.setIcon(icon)
    widget.setToolTip(tooltip)
    widget.setAutoRaise(True)
    return widget


def chip(text: str, status: str, parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setProperty("kc", "chip")
    widget.setProperty("status", status)
    return widget
