"""Wizard pages shown inside the main window.

Each page is a plain widget with a section label, a heading, an optional
description and its controls. Pages read and write the shared
:class:`configurator.core.project.Selection` on the window, so the window owns
the flow and the pages own their controls.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPlainTextEdit,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import project
from . import widgets


def app_label(app: project.App) -> str:
    if app.section == "remove":
        return f"Remove {app.name}"
    if app.section == "flatpaks":
        return f"{app.name}  (Flatpak, installed per user)"
    if app.section == "local_rpms":
        return f"{app.name}  (local RPM)"
    if app.name in project.RPMFUSION_APPS:
        return f"{app.name}  (needs RPM Fusion)"
    return app.name


class WizardPage(QWidget):
    title = ""
    description = ""

    def __init__(self, wizard, parent: QWidget | None = None):
        super().__init__(parent)
        self.wz = wizard
        self.setProperty("kc", "body")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(12, 12, 12, 12)
        self.body.setSpacing(12)
        self.body.addWidget(widgets.section_label(self.title, self))
        if self.description:
            self.body.addWidget(widgets.label(self.description, "muted", self))

    def add_heading(self, text: str) -> QLabel:
        heading = QLabel(text, self)
        heading.setWordWrap(True)
        font = heading.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        heading.setFont(font)
        self.body.addWidget(heading)
        return heading

    def on_enter(self) -> None:
        """Called every time the page becomes current."""

    def primary_input(self) -> QWidget | None:
        return None


class BasePage(WizardPage):
    title = "BASE IMAGE"

    def __init__(self, wizard):
        super().__init__(wizard)
        self.add_heading("Welcome to KineticOS Image Configurator")
        self.body.addWidget(
            widgets.label(
                "This wizard configures and builds your Kineticos image. Choose the "
                "base image that matches your GPU.",
                "muted",
                self,
            )
        )
        self._first: QWidget | None = None
        for ref, description in wizard.base_descriptions.items():
            radio = QRadioButton(ref, self)
            radio.setChecked(wizard.state.base_image == ref)
            radio.toggled.connect(lambda checked, r=ref: self._pick(r, checked))
            note = widgets.label(description, "muted", self)
            note.setContentsMargins(24, 0, 0, 0)
            self.body.addWidget(radio)
            self.body.addWidget(note)
            if self._first is None:
                self._first = radio
        self.body.addStretch(1)

    def _pick(self, ref: str, checked: bool) -> None:
        if checked:
            self.wz.state.base_image = ref

    def primary_input(self) -> QWidget | None:
        return self._first


class ModulePage(WizardPage):
    def __init__(self, wizard, module: project.Module):
        self.module = module
        self._removal_page = all(app.section == "remove" for app in module.apps)
        self.title = module.name.upper()
        self.description = (
            "Choose preinstalled packages to remove from your image."
            if self._removal_page
            else "Choose the software to include in your image."
        )
        super().__init__(wizard)
        self.add_heading("Packages to remove" if self._removal_page else module.name.title())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        card = widgets.card(parent=scroll)
        card.setMinimumWidth(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        if module.description:
            card_layout.addWidget(widgets.label(module.description, "muted", card))

        chosen = wizard.state.apps.get(module.name, set())
        self.boxes: list[tuple[project.App, QCheckBox]] = []
        for app in module.apps:
            box = QCheckBox(app_label(app), card)
            box.setChecked(app.name in chosen)
            box.toggled.connect(self._sync)
            card_layout.addWidget(box)
            self.boxes.append((app, box))
        card_layout.addStretch(1)
        scroll.setWidget(card)
        self.body.addWidget(scroll, 1)

    def _sync(self, *_args) -> None:
        selected = {app.name for app, box in self.boxes if box.isChecked()}
        if self.module.name in self.wz.state.removal_apps:
            self.wz.state.disable_removals = False
        if selected:
            self.wz.state.apps[self.module.name] = selected
        else:
            self.wz.state.apps.pop(self.module.name, None)

    def primary_input(self) -> QWidget | None:
        return self.boxes[0][1] if self.boxes else None


class OptionalPage(WizardPage):
    title = "OPTIONAL REPOSITORIES"
    description = (
        "Keep these repositories enabled, or disable ones that no selected app needs."
    )

    def __init__(self, wizard):
        super().__init__(wizard)
        self.add_heading("Optional repositories and removals")
        self.rpm_box = QCheckBox("Disable RPM Fusion (free and nonfree repos)", self)
        self.terra_box = QCheckBox("Disable Terra (repos only)", self)
        self.removals_box = QCheckBox("Disable the selected package removals", self)
        self.brave_box = QCheckBox("Disable the Brave browser repository", self)
        self.vivaldi_box = QCheckBox("Disable the Vivaldi repository", self)
        self.rpm_box.toggled.connect(
            lambda checked: setattr(self.wz.state, "disable_rpmfusion", checked)
        )
        self.terra_box.toggled.connect(
            lambda checked: setattr(self.wz.state, "disable_terra", checked)
        )
        self.removals_box.toggled.connect(
            lambda checked: setattr(self.wz.state, "disable_removals", checked)
        )
        self.brave_box.toggled.connect(
            lambda checked: setattr(self.wz.state, "disable_brave_repo", checked)
        )
        self.vivaldi_box.toggled.connect(
            lambda checked: setattr(self.wz.state, "disable_vivaldi_repo", checked)
        )
        for box in (
            self.rpm_box,
            self.terra_box,
            self.removals_box,
            self.brave_box,
            self.vivaldi_box,
        ):
            self.body.addWidget(box)
        self.body.addStretch(1)

    def on_enter(self) -> None:
        asked = project.questions(self.wz.state)
        for name, box, state in (
            ("rpmfusion", self.rpm_box, self.wz.state.disable_rpmfusion),
            ("terra", self.terra_box, self.wz.state.disable_terra),
            ("removals", self.removals_box, self.wz.state.disable_removals),
            ("brave", self.brave_box, self.wz.state.disable_brave_repo),
            ("vivaldi", self.vivaldi_box, self.wz.state.disable_vivaldi_repo),
        ):
            box.setChecked(state)
            box.setVisible(name in asked)

    def primary_input(self) -> QWidget | None:
        for box in (
            self.rpm_box,
            self.terra_box,
            self.removals_box,
            self.brave_box,
            self.vivaldi_box,
        ):
            if box.isVisible():
                return box
        return None


class ReviewPage(WizardPage):
    title = "REVIEW"
    description = "Review your choices before writing the project configuration."

    def __init__(self, wizard):
        super().__init__(wizard)
        self.add_heading("Review")
        self.body.addWidget(
            widgets.label(
                "These changes are written to profile.yaml and modules/*.yaml, then "
                "dcli-bootc gen runs. You can build the image from the app next.",
                "muted",
                self,
            )
        )
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setProperty("kc", "console")
        self.body.addWidget(self.text, 1)

    def on_enter(self) -> None:
        self.text.setPlainText(summary(self.wz))

    def primary_input(self) -> QWidget | None:
        return self.text


def summary(wizard) -> str:
    state = wizard.state
    lines = [f"Base image: {state.base_image}", ""]
    for name, enabled in project.resolve(wizard.profile, state):
        if not enabled:
            lines.append(f"off   {name}")
            continue
        apps = sorted(state.apps.get(name, ()))
        module = wizard.modules.get(name)
        removal_names = (
            {app.name for app in module.apps if app.section == "remove"}
            if module
            else set()
        )
        display_apps = [f"remove {app}" if app in removal_names else app for app in apps]
        lines.append(
            f"on    {name}: {', '.join(display_apps) if display_apps else 'default'}"
        )
    return "\n".join(lines)
