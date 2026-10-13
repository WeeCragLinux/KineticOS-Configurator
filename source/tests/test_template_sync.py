from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from configurator import template_sync


class TemplateSyncTests(unittest.TestCase):
    def test_profile_adds_and_removes_entries_without_changing_local_toggles(self) -> None:
        base = (
            "base_image: upstream\n"
            "enabled_modules:\n"
            "- base\n"
            "- apps\n"
            "- obsolete\n"
        )
        local = (
            "base_image: user-choice\n"
            "enabled_modules:\n"
            "- base\n"
            "#- apps\n"
            "- obsolete\n"
        )
        upstream = (
            "base_image: changed-upstream\n"
            "enabled_modules:\n"
            "- base\n"
            "- apps\n"
            "#- newly-added\n"
        )

        merged, summary = template_sync.merge_profile_entries(base, local, upstream)

        self.assertIn("base_image: user-choice", merged)
        self.assertIn("#- apps", merged)
        self.assertIn("#- newly-added", merged)
        self.assertNotIn("obsolete", merged)
        self.assertEqual((summary.added, summary.removed), (1, 1))

    def test_module_sync_only_imports_new_and_removed_list_entries(self) -> None:
        base = (
            "description: original\n"
            "packages:\n"
            "  - stay\n"
            "  - remove-upstream\n"
            "  - user-kept\n"
            "flatpaks: []\n"
        )
        local = (
            "description: user-edited\n"
            "packages:\n"
            "  #- stay\n"
            "  - remove-upstream\n"
            "  #- user-kept\n"
            "flatpaks: []\n"
        )
        upstream = (
            "description: updated upstream\n"
            "packages:\n"
            "  - stay # upstream changed this existing entry\n"
            "  - new-package\n"
            "flatpaks:\n"
            "  - new-flatpak\n"
            "local_rpms:\n"
            "  - new-rpm\n"
        )

        merged, summary = template_sync.merge_module_entries(base, local, upstream)

        self.assertIn("description: user-edited", merged)
        self.assertIn("  #- stay", merged)
        self.assertNotIn("remove-upstream", merged)
        self.assertIn("  #- user-kept", merged)
        self.assertIn("  - new-package", merged)
        self.assertIn("  - new-flatpak", merged)
        self.assertIn("local_rpms:", merged)
        self.assertIn("  - new-rpm", merged)
        self.assertEqual((summary.added, summary.removed, summary.retained), (3, 1, 1))

    def test_project_sync_keeps_locally_toggled_module_when_upstream_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "modules").mkdir()
            (root / "profile.yaml").write_text(
                "enabled_modules:\n- base\n#- old-module\n"
            )
            (root / "modules" / "old-module.yaml").write_text(
                "description: old module\npackages: []\n"
            )
            base = {
                "profile.yaml": "enabled_modules:\n- base\n- old-module\n",
                "modules/old-module.yaml": "description: old module\npackages: []\n",
            }
            upstream = {"profile.yaml": "enabled_modules:\n- base\n"}

            summary = template_sync.merge_project_entries(root, base, upstream)

            self.assertTrue((root / "modules" / "old-module.yaml").exists())
            self.assertIn("#- old-module", (root / "profile.yaml").read_text())
            self.assertEqual(summary.retained, 2)


if __name__ == "__main__":
    unittest.main()
