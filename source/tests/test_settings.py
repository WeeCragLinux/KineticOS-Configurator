from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configurator.core import settings as settings_module
from configurator.core.settings import Settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.home = Path(self.tempdir.name)
        # Keep tests away from the developer's real legacy config file.
        patcher = patch.object(
            settings_module,
            "legacy_settings_path",
            return_value=self.home / "missing-legacy.json",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def path(self, name: str = "settings.ini") -> Path:
        return self.home / name

    def test_defaults_when_missing(self) -> None:
        settings = Settings(self.path())
        self.assertFalse(settings.system_title_bar)
        self.assertIsNone(settings.checkout_path)

    def test_round_trip_and_immediate_save(self) -> None:
        path = self.path()
        settings = Settings(path)
        settings.set_system_title_bar(True)
        settings.set_checkout_path(self.home / "project")

        saved = path.read_text()
        self.assertIn("systemTitleBar", saved)

        reloaded = Settings(path)
        self.assertTrue(reloaded.system_title_bar)
        self.assertEqual(reloaded.checkout_path, (self.home / "project").resolve())

    def test_malformed_value_falls_back_to_default(self) -> None:
        path = self.path()
        path.write_text("[window]\nsystemTitleBar = not-a-bool\n")
        self.assertFalse(Settings(path).system_title_bar)

    def test_reads_checkout_from_legacy_json_once(self) -> None:
        path = self.path()
        legacy_dir = self.home / "kineticos-image-builder"
        legacy_dir.mkdir(parents=True)
        legacy = legacy_dir / "settings.json"
        legacy.write_text('{"checkout_path": "/tmp/old-project"}')

        with patch.object(
            settings_module, "legacy_settings_path", return_value=legacy
        ):
            settings = Settings(path)

        self.assertEqual(str(settings.checkout_path), "/tmp/old-project")

    def test_save_failure_is_not_fatal(self) -> None:
        # A path whose parent cannot be created must not raise.
        settings = Settings(Path("/proc/definitely-not-writable/settings.ini"))
        settings.set_system_title_bar(True)  # must not raise
        self.assertTrue(settings.system_title_bar)


if __name__ == "__main__":
    unittest.main()
