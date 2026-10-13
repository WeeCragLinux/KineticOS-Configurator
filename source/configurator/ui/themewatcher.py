"""Follow the desktop theme, including live changes.

Adds what Qt does not do on its own:

- watches ``~/.config/gtk-4.0/`` and local ``@import`` targets and rebuilds the
  application stylesheet when a ``.css`` file changes (debounced 200 ms), so a
  running theme generator is picked up;
- re-applies on the Qt colour-scheme change signal;
- derives the window colours from the user's ``gtk.css`` ``@define-color``
  entries when present, so GNOME-style themes match;
- applies the desktop monospace font to the mono classes;
- emits :pyattr:`changed` after every re-theme.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication

from ..core import theme

STYLESHEET = Path(__file__).resolve().parent.parent / "assets" / "style.qss"
MONO_FALLBACK = ['"Adwaita Mono"', '"JetBrains Mono"', "monospace"]
DEBOUNCE_MS = 200
GTK_DEFINES = ("window_bg_color", "window_fg_color", "accent_bg_color", "accent_fg_color")


def gtk_config_dir() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    base = Path(configured) if configured else Path.home() / ".config"
    return base.expanduser() / "gtk-4.0"


def _rgb(color: QColor) -> tuple[int, int, int]:
    return color.red(), color.green(), color.blue()


def _define(overrides: dict[str, str], name: str, fallback: QColor) -> QColor:
    parsed = theme.parse_hex(overrides.get(name, ""))
    return QColor(*parsed) if parsed else fallback


class ThemeWatcher(QObject):
    """Owns the application stylesheet and re-applies it on theme changes."""

    changed = Signal()

    def __init__(self, application, parent: QObject | None = None):
        super().__init__(parent)
        self._application = application
        self._colors: dict[str, str] = {}
        self._dark = False

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._schedule)
        self._watcher.directoryChanged.connect(self._schedule)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._apply)

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._schedule)

        self._reload_watches()
        self._apply()

    def colors(self) -> dict[str, str]:
        return dict(self._colors)

    def is_dark(self) -> bool:
        return self._dark

    def _schedule(self, *_args) -> None:
        self._reload_watches()
        self._timer.start()

    def _reload_watches(self) -> None:
        directory = gtk_config_dir()
        wanted: list[str] = []
        if directory.is_dir():
            wanted.append(str(directory))
            for entry in sorted(directory.glob("*.css")):
                wanted.append(str(entry))
                try:
                    text = entry.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for imported in theme.parse_gtk_imports(text, directory):
                    if imported.is_file():
                        wanted.append(str(imported))

        current = set(self._watcher.files()) | set(self._watcher.directories())
        for path in wanted:
            if path not in current:
                self._watcher.addPath(path)

    def _gtk_overrides(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        directory = gtk_config_dir()
        stylesheet = directory / "gtk.css"
        try:
            text = stylesheet.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return overrides
        # Parse errors in the user's file are ignored; only valid entries count.
        overrides.update(theme.parse_gtk_defines(text))
        for imported in theme.parse_gtk_imports(text, directory):
            try:
                overrides.update(
                    theme.parse_gtk_defines(imported.read_text(errors="replace"))
                )
            except OSError:
                continue
        return overrides

    def _detect_dark(self, background: QColor) -> bool:
        scheme = getattr(QGuiApplication.styleHints(), "colorScheme", None)
        if scheme is not None:
            try:
                value = QGuiApplication.styleHints().colorScheme()
                if value == Qt.ColorScheme.Dark:
                    return True
                if value == Qt.ColorScheme.Light:
                    return False
            except (TypeError, AttributeError):
                pass
        return theme.is_dark(_rgb(background))

    def _mono_family(self) -> str:
        family = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        ).family()
        if family:
            return f'"{family}", ' + ", ".join(MONO_FALLBACK)
        return ", ".join(MONO_FALLBACK)

    def _apply(self) -> None:
        palette = self._application.palette()
        overrides = self._gtk_overrides()
        background = _define(
            overrides, "window_bg_color", palette.color(palette.ColorRole.Window)
        )
        foreground = _define(
            overrides, "window_fg_color", palette.color(palette.ColorRole.WindowText)
        )
        accent = _define(
            overrides, "accent_bg_color", palette.color(palette.ColorRole.Highlight)
        )
        accent_foreground = _define(
            overrides,
            "accent_fg_color",
            palette.color(palette.ColorRole.HighlightedText),
        )

        self._dark = self._detect_dark(background)
        colors = theme.build_colors(
            _rgb(foreground), _rgb(background), _rgb(accent), _rgb(accent_foreground)
        )
        colors["kc_mono_family"] = self._mono_family()

        try:
            template = STYLESHEET.read_text(encoding="utf-8")
        except OSError:
            return
        self._application.setStyleSheet(theme.substitute(template, colors))
        self._colors = colors
        self.changed.emit()
