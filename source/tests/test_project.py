from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from configurator.core import project


DEFAULT_IMAGE = "ghcr.io/theblack-don/kineticos:default"


class ProjectTests(unittest.TestCase):
    def make_project(self, enabled: bool = False) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "modules").mkdir()
        app_module = "- apps" if enabled else "#- apps"
        (root / "profile.yaml").write_text(
            f"base_image: {DEFAULT_IMAGE}\n"
            "enabled_modules:\n"
            "- base\n"
            "- rpmfusion\n"
            "- terra\n"
            f"{app_module}\n"
        )
        (root / "modules" / "base.yaml").write_text(
            "description: base\npackages: []\n"
        )
        (root / "modules" / "rpmfusion.yaml").write_text(
            "description: RPM Fusion repos\npackages: []\n"
        )
        (root / "modules" / "terra.yaml").write_text(
            "description: Terra repos\npackages: []\n"
        )
        (root / "modules" / "apps.yaml").write_text(
            "description: apps\npackages:\n  #- sample-app\n"
        )
        return root

    def test_reads_enabled_and_disabled_apps(self) -> None:
        root = self.make_project()
        profile = project.Profile(root)
        modules = project.load_modules(root)
        self.assertEqual(profile.base_image, DEFAULT_IMAGE)
        self.assertFalse(modules["apps"].apps[0].enabled)

        app_file = root / "modules" / "apps.yaml"
        app_file.write_text(app_file.read_text().replace("#- sample-app", "- sample-app"))
        self.assertTrue(project.load_modules(root)["apps"].apps[0].enabled)

    def test_disabled_module_is_enabled_only_when_an_app_is_selected(self) -> None:
        root = self.make_project()
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            app_modules={"apps"},
        )

        self.assertEqual(
            project.resolve(profile, selection),
            [("base", True), ("rpmfusion", True), ("terra", True), ("apps", False)],
        )
        selection.apps["apps"] = {"sample-app"}
        self.assertEqual(project.resolve(profile, selection)[-1], ("apps", True))

    def test_new_modules_are_added_disabled_and_baseline_is_enabled(self) -> None:
        root = self.make_project()
        profile_path = root / "profile.yaml"
        profile_path.write_text(
            "base_image: example\n"
            "enabled_modules:\n"
            "- base\n"
            "#- rpmfusion\n"
            "#- terra\n"
        )
        profile = project.Profile(root)
        profile.ensure_modules({"apps", "new-apps"})

        self.assertEqual(
            profile.entries,
            [
                ("base", True),
                ("rpmfusion", True),
                ("terra", True),
                ("apps", False),
                ("new-apps", False),
            ],
        )

    def test_profile_parser_and_save_preserve_comments_and_entry_formatting(self) -> None:
        root = self.make_project()
        profile_path = root / "profile.yaml"
        original = (
            "# project comment\n"
            "base_image: old-image  # keep this note\n"
            "enabled_modules:\n"
            "- base # always on\n"
            "# explanatory comment stays in place\n"
            "#- rpmfusion # was disabled\n"
            "  # - terra # was disabled too\n"
            "- apps # app selection\n"
            "package_manager: dnf\n"
            "# end comment\n"
        )
        profile_path.write_text(original)
        profile = project.Profile(root)
        self.assertEqual(
            profile.entries,
            [
                ("base", True),
                ("rpmfusion", False),
                ("terra", False),
                ("apps", True),
            ],
        )

        profile.save(
            "new-image",
            [
                ("base", True),
                ("rpmfusion", True),
                ("terra", False),
                ("apps", False),
                ("discovered", False),
            ],
        )
        saved = profile_path.read_text()

        self.assertIn("# project comment\n", saved)
        self.assertIn("# explanatory comment stays in place\n", saved)
        self.assertIn("package_manager: dnf\n# end comment\n", saved)
        self.assertIn("base_image: new-image  # keep this note", saved)
        self.assertIn("- rpmfusion # was disabled", saved)
        self.assertIn("  # - terra # was disabled too", saved)
        self.assertIn("#- apps # app selection", saved)
        self.assertIn("#- discovered", saved)
        self.assertEqual(project.Profile(root).base_image, "new-image")

    def test_no_selected_apps_keeps_only_baseline_modules_enabled(self) -> None:
        root = self.make_project(enabled=True)
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            app_modules={"apps"},
        )

        project.apply(root, selection, modules, profile)

        self.assertEqual(
            project.Profile(root).entries,
            [
                ("base", True),
                ("rpmfusion", True),
                ("terra", True),
                ("apps", False),
            ],
        )

    def test_removals_are_opt_in_per_package_and_can_be_disabled_at_the_end(self) -> None:
        root = self.make_project()
        profile_path = root / "profile.yaml"
        profile_path.write_text(profile_path.read_text() + "- removals\n")
        removals_path = root / "modules" / "removals.yaml"
        removals_path.write_text(
            "description: optional package removals\n"
            "packages: []\n"
            "remove:\n"
            "  #- dolphin\n"
            "  #- spectacle\n"
        )
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            app_modules={"apps", "removals"},
            removal_apps={"removals": {"dolphin", "spectacle"}},
        )

        # An enabled profile entry alone must not enable an empty removals module.
        self.assertFalse(dict(project.resolve(profile, selection))["removals"])
        self.assertNotIn("removals", project.questions(selection))

        selection.apps["removals"] = {"dolphin"}
        self.assertTrue(dict(project.resolve(profile, selection))["removals"])
        self.assertIn("removals", project.questions(selection))
        self.assertNotIn("dolphin", selection.chosen())
        project.apply(root, selection, modules, profile)

        self.assertIn("  - dolphin\n", removals_path.read_text())
        self.assertIn("  #- spectacle\n", removals_path.read_text())
        self.assertIn(("removals", True), project.Profile(root).entries)

        selection.disable_removals = True
        project.apply(root, selection, modules, project.Profile(root))

        self.assertFalse(dict(project.resolve(project.Profile(root), selection))["removals"])
        self.assertIn("  #- dolphin\n", removals_path.read_text())
        self.assertIn("  #- spectacle\n", removals_path.read_text())
        self.assertIn(("removals", False), project.Profile(root).entries)

    def test_required_repositories_cannot_be_disabled(self) -> None:
        root = self.make_project()
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            apps={"content": {"vlc"}, "gaming": {"terra-mangohud"}},
            app_modules={"content", "gaming"},
            disable_rpmfusion=True,
            disable_terra=True,
        )

        self.assertNotIn("rpmfusion", project.questions(selection))
        self.assertNotIn("terra", project.questions(selection))
        self.assertEqual(
            project.resolve(profile, selection)[:3],
            [("base", True), ("rpmfusion", True), ("terra", True)],
        )

    def test_browser_apps_enable_their_pre_install_repo_commands(self) -> None:
        root = self.make_project()
        browser_path = root / "modules" / "browsers.yaml"
        browser_path.write_text(
            "description: browsers\n"
            "packages:\n"
            "  #- brave-browser\n"
            "  #- brave-origin\n"
            "  #- vivaldi-stable\n"
            "scripts:\n"
            "  pre: |\n"
            "    # dnf config-manager addrepo --from-repofile="
            "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo\n"
            "    # dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo\n"
        )
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            apps={"browsers": {"brave-origin"}},
            app_modules={"browsers"},
        )

        project.apply(root, selection, modules, profile)

        saved = browser_path.read_text()
        self.assertIn("  - brave-origin", saved)
        self.assertIn(
            "    dnf config-manager addrepo --from-repofile="
            "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo",
            saved,
        )
        self.assertIn(
            "    # dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo",
            saved,
        )
        self.assertLess(saved.index("  pre: |"), saved.index("    dnf config-manager"))

    def test_unused_active_browser_repo_can_be_disabled(self) -> None:
        root = self.make_project()
        browser_path = root / "modules" / "browsers.yaml"
        browser_path.write_text(
            "description: browsers\n"
            "packages:\n"
            "  #- brave-browser\n"
            "  #- brave-origin\n"
            "scripts:\n"
            "  pre: |\n"
            "    dnf config-manager addrepo --from-repofile="
            "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo\n"
            "    # dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo\n"
        )
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            app_modules={"browsers"},
            brave_repo_enabled=True,
            disable_brave_repo=True,
        )

        self.assertIn("brave", project.questions(selection))
        project.apply(root, selection, modules, profile)

        saved = browser_path.read_text()
        self.assertIn(
            "    # dnf config-manager addrepo --from-repofile="
            "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo",
            saved,
        )

    def test_selected_helium_enables_its_nested_copr_entry(self) -> None:
        root = self.make_project()
        module_path = root / "modules" / "browsers.yaml"
        module_path.write_text(
            "description: browsers\n"
            "packages:\n"
            "  #- helium-bin\n"
            "repos:\n"
            "  copr:\n"
            "    #- imput/helium\n"
        )
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            apps={"browsers": {"helium-bin"}},
            app_modules={"browsers"},
        )

        project.apply(root, selection, modules, profile)

        saved = module_path.read_text()
        self.assertIn("  - imput/helium", saved)

    def test_vivaldi_app_enables_its_pre_install_repo_command(self) -> None:
        root = self.make_project()
        browser_path = root / "modules" / "browsers.yaml"
        browser_path.write_text(
            "description: browsers\n"
            "packages:\n"
            "  #- vivaldi-stable\n"
            "scripts:\n"
            "  pre: |\n"
            "    # dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo\n"
        )
        profile = project.Profile(root)
        modules = project.load_modules(root)
        profile.ensure_modules(modules)
        selection = project.Selection(
            base_image=profile.base_image,
            apps={"browsers": {"vivaldi-stable"}},
            app_modules={"browsers"},
        )

        project.apply(root, selection, modules, profile)

        saved = browser_path.read_text()
        self.assertIn("  - vivaldi-stable", saved)
        self.assertIn(
            "    dnf config-manager addrepo --from-repofile="
            "https://repo.vivaldi.com/stable/vivaldi-fedora.repo",
            saved,
        )


if __name__ == "__main__":
    unittest.main()
