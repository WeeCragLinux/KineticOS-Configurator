"""The help window, showing the packaged HELP.md (F1)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QTextBrowser, QWidget

from .secondary import SecondaryWindow

FALLBACK = (
    "# KineticOS Configurator\n\n"
    "Help text is unavailable in this build. Run the wizard to choose a project, "
    "a base image, app modules and optional repositories, then review and write "
    "your configuration and build the image.\n"
)


def help_path() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[3] / "HELP.md",
        Path("/usr/share/doc/KineticOS-Configurator/HELP.md"),
        Path("/usr/share/doc/kinetic-configurator/HELP.md"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class HelpWindow(SecondaryWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Help", parent)
        self.resize(720, 560)
        self.setModal(False)

        path = help_path()
        try:
            text = path.read_text(encoding="utf-8") if path else FALLBACK
        except OSError:
            text = FALLBACK

        browser = QTextBrowser(self.body)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(text)
        self.body_layout.addWidget(browser, 1)
