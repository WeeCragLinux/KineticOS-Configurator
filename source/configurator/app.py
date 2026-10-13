from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from . import project
from .workspace import ProjectChooser, is_project

BASE_DESCRIPTIONS = {
    "ghcr.io/theblack-don/kineticos:default": "AMD and Intel GPUs",
    "ghcr.io/theblack-don/kineticos:nvidia": (
        "NVIDIA GPUs based on Turing or newer: GTX 16 series, and RTX 20, 30, 40 and 50 series"
    ),
    "ghcr.io/theblack-don/kineticos:nvidia-legacy": "NVIDIA GPUs older than the 10 series",
}


def app_label(app: project.App) -> str:
    if app.section == "flatpaks":
        return f"{app.name}  (Flatpak, installed per user)"
    if app.section == "local_rpms":
        return f"{app.name}  (local RPM)"
    if app.name in project.RPMFUSION_APPS:
        return f"{app.name}  (needs RPM Fusion)"
    return app.name


class Page(QWizardPage):
    def __init__(self, wizard: Wizard, banner_title: str, banner_text: str):
        super().__init__(wizard)
        self.wz = wizard
        # Use a compact in-page header instead of QWizard's tall native title area.
        self.setTitle("")
        self.setSubTitle("")

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        banner = QFrame(self)
        banner.setObjectName("pageBanner")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(20, 12, 20, 12)
        banner_layout.setSpacing(4)

        title = QLabel(banner_title, banner)
        title.setObjectName("pageBannerTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        text = QLabel(banner_text, banner)
        text.setWordWrap(True)
        banner_layout.addWidget(title)
        banner_layout.addWidget(text)
        banner.setStyleSheet(
            "QFrame#pageBanner {"
            " background-color: palette(alternate-base);"
            " border-bottom: 1px solid palette(mid);"
            "}"
            "QFrame#pageBanner QLabel { background: transparent; border: none; }"
        )
        page_layout.addWidget(banner)

        body = QWidget(self)
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(20, 16, 20, 14)
        self.body_layout.setSpacing(10)
        page_layout.addWidget(body, 1)

    def add_section_heading(self, text: str) -> None:
        heading = QLabel(text, self)
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.body_layout.addWidget(heading)

    def nextId(self) -> int:
        flow = self.wz.flow()
        if self not in flow:
            return self.wz.page_ids[self.wz.review_page]
        index = flow.index(self)
        if index + 1 < len(flow):
            return self.wz.page_ids[flow[index + 1]]
        return -1


class BasePage(Page):
    def __init__(self, wizard: Wizard):
        super().__init__(
            wizard,
            "Welcome to KineticOS Image Configurator",
            "This wizard will guide you through configuring and building your Kineticos image.",
        )
        self.add_section_heading("Base image")
        self.body_layout.addWidget(
            QLabel("Choose the Kineticos image that matches your GPU.", self)
        )
        for ref, description in BASE_DESCRIPTIONS.items():
            radio = QRadioButton(ref)
            radio.toggled.connect(lambda checked, r=ref: self.pick(r, checked))
            radio.setChecked(self.wz.state.base_image == ref)
            note = QLabel(description)
            note.setWordWrap(True)
            note.setContentsMargins(24, 0, 0, 10)
            self.body_layout.addWidget(radio)
            self.body_layout.addWidget(note)
        self.body_layout.addStretch()

    def pick(self, ref: str, checked: bool) -> None:
        if checked:
            self.wz.state.base_image = ref
            self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self.wz.state.base_image is not None


class ModulePage(Page):
    def __init__(self, wizard: Wizard, module: project.Module):
        super().__init__(
            wizard,
            "KineticOS Image Configurator",
            "Choose the software to include in your image.",
        )
        self.module = module
        self.add_section_heading(module.name)
        description = QLabel(module.description, self)
        description.setWordWrap(True)
        self.body_layout.addWidget(description)
        chosen = {app.name for app in module.apps if app.enabled}
        self.boxes: list[tuple[project.App, QCheckBox]] = []
        for app in module.apps:
            box = QCheckBox(app_label(app))
            box.setChecked(app.name in chosen)
            box.toggled.connect(self.sync)
            self.body_layout.addWidget(box)
            self.boxes.append((app, box))
        self.body_layout.addStretch()

    def sync(self, *_) -> None:
        selected = {app.name for app, box in self.boxes if box.isChecked()}
        if selected:
            self.wz.state.apps[self.module.name] = selected
        else:
            self.wz.state.apps.pop(self.module.name, None)


class OptionalPage(Page):
    def __init__(self, wizard: Wizard):
        super().__init__(
            wizard,
            "KineticOS Image Configurator",
            "Choose whether to keep optional package repositories enabled.",
        )
        self.add_section_heading("Optional modules")
        description = QLabel(
            "These modules are on by default, and none of your selected apps need them.", self
        )
        description.setWordWrap(True)
        self.body_layout.addWidget(description)
        self.rpm_box = QCheckBox("Disable RPM Fusion (free and nonfree repos)")
        self.terra_box = QCheckBox("Disable Terra (repos only)")
        self.rpm_box.toggled.connect(lambda c: setattr(self.wz.state, "disable_rpmfusion", c))
        self.terra_box.toggled.connect(lambda c: setattr(self.wz.state, "disable_terra", c))
        self.body_layout.addWidget(self.rpm_box)
        self.body_layout.addWidget(self.terra_box)
        self.body_layout.addStretch()

    def initializePage(self) -> None:
        asked = project.questions(self.wz.state)
        self.rpm_box.setVisible("rpmfusion" in asked)
        self.rpm_box.setChecked(self.wz.state.disable_rpmfusion)
        self.terra_box.setVisible("terra" in asked)
        self.terra_box.setChecked(self.wz.state.disable_terra)


class ReviewPage(Page):
    def __init__(self, wizard: Wizard):
        super().__init__(
            wizard,
            "KineticOS Image Configurator",
            "Review your choices before writing the project configuration.",
        )
        self.add_section_heading("Review")
        review_description = QLabel(
            "These changes are written to profile.yaml and modules/*.yaml, then "
            "dcli-bootc gen runs. You can build the image from the app next.",
            self,
        )
        review_description.setWordWrap(True)
        self.body_layout.addWidget(review_description)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.body_layout.addWidget(self.text)

    def initializePage(self) -> None:
        self.text.setPlainText(summary(self.wz))


def summary(wizard: Wizard) -> str:
    state = wizard.state
    lines = [f"Base image: {state.base_image}", ""]
    for name, on in project.resolve(wizard.profile, state):
        if not on:
            lines.append(f"off   {name}")
            continue
        apps = sorted(state.apps.get(name, ()))
        lines.append(f"on    {name}: {', '.join(apps) if apps else 'default'}")
    return "\n".join(lines)


class CommandDialog(QDialog):
    """Run a long dcli-bootc command and display its live output."""

    def __init__(self, title: str, command: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 480)
        self.success = False
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.cancel_button = QPushButton("Cancel", self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Command output:"))
        layout.addWidget(self.output)
        layout.addWidget(self.cancel_button)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.on_process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.cancel_button.clicked.connect(self.cancel_or_close)
        self.command = command

    def run(self) -> bool:
        self.process.start(self.command[0], self.command[1:])
        self.exec()
        return self.success

    def read_output(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if text:
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.insertPlainText(text)
            self.output.ensureCursorVisible()

    def on_process_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self.read_output()
        self.success = (
            exit_code == 0 and _exit_status == QProcess.ExitStatus.NormalExit
        )
        self.cancel_button.setText("Close")

    def process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.output.appendPlainText("Could not start command. Is dcli-bootc installed?")
            self.success = False
            self.cancel_button.setText("Close")

    def cancel_or_close(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.accept()
            return
        answer = QMessageBox.question(
            self,
            "Stop command?",
            "The command is still running. Stop it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
            self.cancel_button.setText("Close")

    def closeEvent(self, event) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            event.accept()
            return
        event.ignore()
        self.cancel_or_close()


class Wizard(QWizard):
    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.profile = project.Profile(root)
        self.modules = project.load_modules(root)
        self.add_new_modules()
        enabled_modules = {name for name, on in self.profile.entries if on}
        self.state = project.Selection(
            base_image=self.profile.base_image,
            originally_enabled_modules={
                name for name, on in self.profile.entries if on
            },
            apps={
                name: {app.name for app in module.apps if app.enabled}
                for name, module in self.modules.items()
                if name in enabled_modules and any(app.enabled for app in module.apps)
            },
        )
        self.page_ids: dict[QWizardPage, int] = {}

        self.setWindowTitle("KineticOS Image Configurator")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setButtonText(QWizard.WizardButton.FinishButton, "Write changes")
        self.resize(760, 600)

        self.base_page = BasePage(self)
        self.add_page(self.base_page)

        self.module_pages: list[ModulePage] = []
        for name, _ in self.profile.entries:
            module = self.modules.get(name)
            if name == "base" or module is None or not module.apps:
                continue
            page = ModulePage(self, module)
            self.add_page(page)
            self.module_pages.append(page)

        self.optional_page = OptionalPage(self)
        self.add_page(self.optional_page)
        self.review_page = ReviewPage(self)
        self.add_page(self.review_page)

    def add_new_modules(self) -> None:
        known = {name for name, _ in self.profile.entries}
        new_modules = sorted(set(self.modules) - known - {"base"})
        if not new_modules:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("New modules found")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        message = QLabel(
            "Select the modules to add to profile.yaml. App modules will remain "
            "disabled unless you select apps from them in the wizard."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        module_list = QListWidget(dialog)
        for name in new_modules:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip(self.modules[name].description)
            module_list.addItem(item)
        layout.addWidget(module_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add selected")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = [
            module_list.item(index).text()
            for index in range(module_list.count())
            if module_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        self.profile.entries.extend((name, False) for name in selected)

    def add_page(self, page: QWizardPage) -> None:
        page_id = len(self.page_ids)
        self.page_ids[page] = page_id
        self.setPage(page_id, page)

    def flow(self) -> list[QWizardPage]:
        pages: list[QWizardPage] = [self.base_page, *self.module_pages]
        if project.questions(self.state):
            pages.append(self.optional_page)
        pages.append(self.review_page)
        return pages

    def accept(self) -> None:
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
        QMessageBox.information(
            self,
            "Done",
            "Files written and dcli-bootc gen completed.",
        )

        build = QMessageBox.question(
            self,
            "Build image now?",
            "Would you like to run dcli-bootc build for this project now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if build == QMessageBox.StandardButton.Yes:
            build_dialog = CommandDialog(
                "Building KineticOS image",
                ["dcli-bootc", "build", "-p", str(self.root), "--no-switch"],
                self,
            )
            if not build_dialog.run():
                QMessageBox.warning(
                    self,
                    "Image build failed",
                    "dcli-bootc build did not complete successfully.\n\n"
                    + build_dialog.output.toPlainText()[-4000:],
                )
                super().accept()
                return

            switch = QMessageBox.question(
                self,
                "Switch to the new image and reboot?",
                "The image built successfully. Switch this computer to the new image and reboot now?\n\n"
                "The current deployment should remain available for rollback.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if switch == QMessageBox.StandardButton.Yes:
                switch_dialog = CommandDialog(
                    "Switching to the new image",
                    [
                        "dcli-bootc",
                        "switch",
                        "-p",
                        str(self.root),
                        "--force",
                        "--reboot",
                    ],
                    self,
                )
                if not switch_dialog.run():
                    QMessageBox.warning(
                        self,
                        "Could not switch image",
                        "dcli-bootc switch did not complete successfully. Check its output and "
                        "your system's bootc permissions.\n\n"
                        + switch_dialog.output.toPlainText()[-4000:],
                    )
        super().accept()


def main(root: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("KineticOS Image Configurator")
    app.setOrganizationName("WeeCragLinux")

    if root is None:
        chooser = ProjectChooser()
        if chooser.exec() != QDialog.DialogCode.Accepted or chooser.checkout is None:
            return 0
        root = chooser.checkout
    elif not is_project(root):
        QMessageBox.critical(
            None,
            "Not an image project",
            f"Choose a folder containing profile.yaml and a modules/ directory.\n\n{root}",
        )
        return 1

    wizard = Wizard(root)
    wizard.show()
    return app.exec()
