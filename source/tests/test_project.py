from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from configurator import project


class ProjectTests(unittest.TestCase):
    def make_project(self, enabled: bool) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "modules").mkdir()
        profile_module = "- apps" if enabled else "#- apps"
        (root / "profile.yaml").write_text(
            "base_image: ghcr.io/example/image:latest\n"
            "enabled_modules:\n"
            "- base\n"
            f"{profile_module}\n"
        )
        (root / "modules" / "base.yaml").write_text(
            "description: base\npackages: []\n"
        )
        (root / "modules" / "apps.yaml").write_text(
            "description: apps\npackages:\n - sample-app\n"
        )
        return root

    def test_reads_base_image_and_enabled_apps(self) -> None:
        root = self.make_project(enabled=True)
        profile = project.Profile(root)
        modules = project.load_modules(root)
        self.assertEqual(profile.base_image, "ghcr.io/example/image:latest")
        self.assertTrue(modules["apps"].apps[0].enabled)

    def test_disabled_module_keeps_its_saved_package_choices(self) -> None:
        root = self.make_project(enabled=False)
        profile = project.Profile(root)
        modules = project.load_modules(root)
        before = (root / "modules" / "apps.yaml").read_text()

        project.apply(
            root,
            project.Selection(
                base_image=profile.base_image,
                originally_enabled_modules={"base"},
            ),
            modules,
            profile,
        )

        self.assertEqual((root / "modules" / "apps.yaml").read_text(), before)
        self.assertIn("#- apps", (root / "profile.yaml").read_text())


if __name__ == "__main__":
    unittest.main()
