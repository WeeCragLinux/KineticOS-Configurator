"""Load the bundled app icon from the package assets.

The standard bundles the icon in a GResource so an uninstalled build still
shows it; for Qt we ship the source SVG in ``configurator/assets`` and render it
on demand.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_PATH = ASSETS / "icon.svg"


def _render_svg(path: Path, size: int) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(path))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def icon_pixmap(size: int = 28, path: Path | None = None) -> QPixmap:
    source = path or ICON_PATH
    if source.suffix.lower() == ".svg":
        try:
            rendered = _render_svg(source, size)
            if not rendered.isNull():
                return rendered
        except (ImportError, ValueError):
            pass
    pixmap = QPixmap(str(source))
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def app_icon() -> QIcon:
    if ICON_PATH.is_file():
        return QIcon(str(ICON_PATH))
    return QIcon.fromTheme("application-x-executable")
