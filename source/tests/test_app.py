from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QRadioButton

from configurator import project
from configurator.app import BASE_DESCRIPTIONS, Wizard


class WizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

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

    def test_all_app_modules_are_pages_and_discover_without_a_prompt(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        wizard = Wizard(root)
        self.addCleanup(wizard.close)

        page_modules = {page.module.name for page in wizard.module_pages}
        states = dict(wizard.profile.entries)
        self.assertEqual(page_modules, {"browsers", "new-apps"})
        self.assertNotIn("base", wizard.state.app_modules)
        self.assertNotIn("base", wizard.state.apps)
        self.assertFalse(states["browsers"])
        self.assertFalse(states["new-apps"])

    def test_review_page_displays_missing_tools_disclaimer(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        wizard = Wizard(root)
        self.addCleanup(wizard.close)

        disclaimer = wizard.review_page.disclaimer.text()
        self.assertIn("does not include a file manager or screenshot tool", disclaimer)

    def test_base_package_entries_are_not_optional_or_rewritten(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        wizard = Wizard(root)
        self.addCleanup(wizard.close)
        base_path = root / "modules" / "base.yaml"
        before = base_path.read_text()
        wizard.state.apps["new-apps"] = {"example-app"}

        project.apply(root, wizard.state, wizard.modules, wizard.profile)

        self.assertEqual(base_path.read_text(), before)
        self.assertIn(("base", True), project.Profile(root).entries)

    def test_optional_repository_visibility_tracks_app_requirements(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        wizard = Wizard(root)
        self.addCleanup(wizard.close)
        page = wizard.optional_page

        page.initializePage()
        self.assertFalse(page.rpm_box.isHidden())
        self.assertFalse(page.terra_box.isHidden())
        self.assertFalse(page.brave_box.isHidden())
        self.assertFalse(page.vivaldi_box.isHidden())

        wizard.state.apps = {"browsers": {"brave-origin"}, "content": {"vlc"}}
        page.initializePage()
        self.assertTrue(page.rpm_box.isHidden())
        self.assertFalse(page.terra_box.isHidden())
        self.assertTrue(page.brave_box.isHidden())
        self.assertFalse(page.vivaldi_box.isHidden())

        wizard.state.apps["browsers"].add("vivaldi-stable")
        wizard.state.apps["gaming"] = {"terra-mangohud"}
        page.initializePage()
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
        wizard = Wizard(root)
        self.addCleanup(wizard.close)

        wizard.optional_page.initializePage()

        self.assertFalse(wizard.optional_page.brave_box.isHidden())
        self.assertTrue(wizard.optional_page.vivaldi_box.isHidden())

    def test_deck_image_is_experimental_and_does_not_replace_default(self) -> None:
        tempdir, root = self.make_project()
        self.addCleanup(tempdir.cleanup)
        wizard = Wizard(root)
        self.addCleanup(wizard.close)
        radio_buttons = wizard.base_page.findChildren(QRadioButton)
        default = next(
            radio
            for radio in radio_buttons
            if radio.text() == "ghcr.io/theblack-don/kineticos:default"
        )

        self.assertTrue(default.isChecked())
        self.assertIn("ghcr.io/theblack-don/kineticos:deck", project.BASE_IMAGES)
        self.assertIn("Very early", BASE_DESCRIPTIONS["ghcr.io/theblack-don/kineticos:deck"])
        self.assertIn(
            "not recommended for normal use",
            BASE_DESCRIPTIONS["ghcr.io/theblack-don/kineticos:deck"],
        )


if __name__ == "__main__":
    unittest.main()
