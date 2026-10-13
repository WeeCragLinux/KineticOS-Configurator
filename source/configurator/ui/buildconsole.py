"""Run a long command and show its live output in a secondary window."""

from __future__ import annotations

from PySide6.QtCore import QProcess
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QWidget

from . import widgets
from .secondary import SecondaryWindow

FLATPAK_PROMPT = "apply these changes to your user flatpak installation?"


class BuildConsole(SecondaryWindow):
    """Runs a command, streams the merged output and answers the Flatpak prompt."""

    def __init__(self, title: str, command: list[str], parent: QWidget | None = None):
        super().__init__(title, parent)
        self.resize(760, 480)
        self.success = False
        self._answered_prompts = 0
        self.command = command

        self.body_layout.addWidget(widgets.label("Command output:", "muted", self.body))

        self.output = QPlainTextEdit(self.body)
        self.output.setReadOnly(True)
        self.output.setProperty("kc", "console")
        self.body_layout.addWidget(self.output, 1)

        self.prompt_controls = QWidget(self.body)
        prompt_layout = QHBoxLayout(self.prompt_controls)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.addWidget(
            widgets.label(
                "Apply these changes to your user Flatpak installation?",
                None,
                self.prompt_controls,
            )
        )
        self.yes_button = QPushButton("Yes", self.prompt_controls)
        self.no_button = QPushButton("No", self.prompt_controls)
        prompt_layout.addStretch(1)
        prompt_layout.addWidget(self.yes_button)
        prompt_layout.addWidget(self.no_button)
        self.prompt_controls.hide()
        self.body_layout.addWidget(self.prompt_controls)

        self.action_button = QPushButton("Cancel", self.body)
        self.body_layout.addWidget(self.action_button, 0)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self.yes_button.clicked.connect(lambda: self._answer("y"))
        self.no_button.clicked.connect(lambda: self._answer("n"))
        self.action_button.clicked.connect(self._cancel_or_close)

    def run(self) -> bool:
        self.process.start(self.command[0], self.command[1:])
        self.exec()
        return self.success

    def _read_output(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if not text:
            return
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()
        self._update_prompt()

    def _update_prompt(self) -> None:
        output = self.output.toPlainText().lower()
        prompt_count = output.count(FLATPAK_PROMPT)
        running = self.process.state() == QProcess.ProcessState.Running
        self.prompt_controls.setVisible(
            running and prompt_count > self._answered_prompts
        )

    def _answer(self, answer: str) -> None:
        if self.process.state() != QProcess.ProcessState.Running:
            return
        self.process.write(f"{answer}\n".encode())
        self._answered_prompts = self.output.toPlainText().lower().count(FLATPAK_PROMPT)
        self.prompt_controls.hide()

    def _on_finished(self, exit_code: int, exit_status) -> None:
        self._read_output()
        self.success = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        self.prompt_controls.hide()
        self.action_button.setText("Close")

    def _on_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.output.appendPlainText(
                "Could not start command. Is dcli-bootc installed?"
            )
            self.success = False
            self.prompt_controls.hide()
            self.action_button.setText("Close")

    def _cancel_or_close(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.accept()
            return
        self._stop()

    def _stop(self) -> None:
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()
        self.action_button.setText("Close")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self.process.state() == QProcess.ProcessState.NotRunning:
            event.accept()
            return
        self._stop()
        event.accept()
