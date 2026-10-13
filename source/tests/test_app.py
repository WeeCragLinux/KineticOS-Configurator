from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QRadioButton

from configurator.core import project
from configurator.core.settings import Settings
from configurator.ui.buildconsole import BuildConsole
from configurator.ui.mainwindow import BASE_DESCRIPTIONS, MainWindow
from configurator.ui.themewatcher import ThemeWatcher


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])
        cls.theme = ThemeWatcher(cls.application)

    def make_project(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        tempdir = tempfile.TemporaryDirectory()
        root = Path(tempdir.name)
        (root / "modules").mkdir()
        (root / "profile.yaml").write_text(
            "base_image: ghcr.io/theblack-don/kineticos:default\n"
            "enabled_modules:\n"
            "- base\n"
            "- rpmfusion\n"
            "- terra\n"
        )
        for name in ("base", "rpmfusion", "terra"):
            if name == "base":
                content = (
                    "description: base\n"
                    "packages:\n"
                    "  - mandatory-base-package\n"
                    "  #- optional-base-entry\n"
                )
            else:
                content = f"description: {name}\npackages: []\n"
            (root / "modules" / f"{name}.yaml").write_text(content)
        (root / "modules" / "browsers.yaml").write_text(
            "description: browser apps\n"
            "packages:\n"
            "  #- brave-browser\n"
            "  #- brave-origin\n"
            "  #- vivaldi-stable\n"
            "scripts:\n"
            "  pre: |\n"
            "    dnf config-manager addrepo --from-repofile="
            "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo\n"
            "    dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo\n"
        )
        (root / "modules" / "new-apps.yaml").write_text(
            "description: discovered apps\npackages:\n  #- example-app\n"
        )
        return tempdir, root

    def make_window(self, root: Path) -> MainWindow:
        window = MainWindow(root, Settings(root / "settings.ini"), self.theme)
        self.addCleanup(window.close)
        return window

    def test_all_app_modules_are_pages_and_discover_without_a_prompt(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        window = self.make_window(root)

        page_modules = {page.module.name for page in window.module_pages}
        states = dict(window.profile.entries)
        self.assertEqual(page_modules, {"browsers", "new-apps"})
        self.assertNotIn("base", window.state.app_modules)
        self.assertNotIn("base", window.state.apps)
        self.assertFalse(states["browsers"])
        self.assertFalse(states["new-apps"])

    def test_review_page_does_not_display_obsolete_tools_warning(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        window = self.make_window(root)
        window.review_page.on_enter()

        page_text = " ".join(
            label.text() for label in window.review_page.findChildren(QLabel)
        )
        self.assertNotIn("file manager", page_text.lower())
        self.assertNotIn("screenshot tool", page_text.lower())

    def test_removal_choices_are_visible_and_can_be_disabled_on_final_options_page(
        self,
    ) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        (root / "modules" / "removals.yaml").write_text(
            "description: Optional removal choices\n"
            "packages: []\n"
            "remove:\n"
            "  #- dolphin\n"
            "  #- spectacle\n"
        )
        window = self.make_window(root)

        page = next(
            page for page in window.module_pages if page.module.name == "removals"
        )
        self.assertEqual(
            [box.text() for _, box in page.boxes], ["Remove dolphin", "Remove spectacle"]
        )
        self.assertTrue(all(not box.isChecked() for _, box in page.boxes))
        self.assertFalse(dict(project.resolve(window.profile, window.state))["removals"])

        page.boxes[0][1].setChecked(True)
        self.assertTrue(dict(project.resolve(window.profile, window.state))["removals"])
        window.optional_page.on_enter()
        self.assertFalse(window.optional_page.removals_box.isHidden())
        self.assertFalse(window.optional_page.removals_box.isChecked())

        window.optional_page.removals_box.setChecked(True)
        self.assertTrue(window.state.disable_removals)
        self.assertFalse(dict(project.resolve(window.profile, window.state))["removals"])

    def test_base_package_entries_are_not_optional_or_rewritten(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        window = self.make_window(root)
        base_path = root / "modules" / "base.yaml"
        before = base_path.read_text()
        window.state.apps["new-apps"] = {"example-app"}

        project.apply(root, window.state, window.modules, window.profile)

        self.assertEqual(base_path.read_text(), before)
        self.assertIn(("base", True), project.Profile(root).entries)

    def test_optional_repository_visibility_tracks_app_requirements(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        window = self.make_window(root)
        page = window.optional_page

        page.on_enter()
        self.assertFalse(page.rpm_box.isHidden())
        self.assertFalse(page.terra_box.isHidden())
        self.assertFalse(page.brave_box.isHidden())
        self.assertFalse(page.vivaldi_box.isHidden())

        window.state.apps = {"browsers": {"brave-origin"}, "content": {"vlc"}}
        page.on_enter()
        self.assertTrue(page.rpm_box.isHidden())
        self.assertFalse(page.terra_box.isHidden())
        self.assertTrue(page.brave_box.isHidden())
        self.assertFalse(page.vivaldi_box.isHidden())

        window.state.apps["browsers"].add("vivaldi-stable")
        window.state.apps["gaming"] = {"terra-mangohud"}
        page.on_enter()
        self.assertTrue(page.terra_box.isHidden())
        self.assertTrue(page.vivaldi_box.isHidden())

    def test_disabled_vendor_repo_is_not_offered_for_disabling(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        browser_path = root / "modules" / "browsers.yaml"
        browser_path.write_text(
            browser_path.read_text().replace(
                "    dnf config-manager addrepo --from-repofile=https://repo.vivaldi.com",
                "    # dnf config-manager addrepo --from-repofile=https://repo.vivaldi.com",
            )
        )
        window = self.make_window(root)

        window.optional_page.on_enter()

        self.assertFalse(window.optional_page.brave_box.isHidden())
        self.assertTrue(window.optional_page.vivaldi_box.isHidden())

    def test_deck_image_is_experimental_and_does_not_replace_default(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        window = self.make_window(root)
        radio_buttons = window.base_page.findChildren(QRadioButton)
        default = next(
            radio
            for radio in radio_buttons
            if radio.text() == "ghcr.io/theblack-don/kineticos:default"
        )

        self.assertTrue(default.isChecked())
        self.assertIn("ghcr.io/theblack-don/kineticos:deck", project.BASE_IMAGES)
        self.assertIn(
            "Very early", BASE_DESCRIPTIONS["ghcr.io/theblack-don/kineticos:deck"]
        )
        self.assertIn(
            "not recommended for normal use",
            BASE_DESCRIPTIONS["ghcr.io/theblack-don/kineticos:deck"],
        )

    def test_build_console_yes_no_buttons_answer_flatpak_prompt(self) -> None:
        for button_name, response in (("yes_button", "y"), ("no_button", "n")):
            with self.subTest(response=response):
                script = (
                    "import sys\n"
                    "print('Apply these changes to your user Flatpak installation? [y/N]', "
                    "end='', flush=True)\n"
                    "print('RECEIVED=' + input())\n"
                )
                console = BuildConsole("Test build", [sys.executable, "-u", "-c", script])
                loop = QEventLoop()
                timeout = QTimer()
                timeout.setSingleShot(True)
                timed_out = []

                def click_response() -> None:
                    if not console.prompt_controls.isHidden():
                        getattr(console, button_name).click()

                def stop_timed_out_process() -> None:
                    timed_out.append(True)
                    console.process.kill()
                    loop.quit()

                console.process.readyReadStandardOutput.connect(click_response)
                console.process.finished.connect(loop.quit)
                timeout.timeout.connect(stop_timed_out_process)
                console.process.start(console.command[0], console.command[1:])
                timeout.start(5000)
                loop.exec()
                timeout.stop()
                console._read_output()

                self.assertFalse(timed_out, "The child process did not receive a response")
                self.assertEqual(console.process.exitCode(), 0)
                self.assertIn(f"RECEIVED={response}", console.output.toPlainText())
                console.close()


if __name__ == "__main__":
    unittest.main()
