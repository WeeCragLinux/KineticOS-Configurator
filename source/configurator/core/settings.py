"""Typed preferences stored in the app's settings.ini.

Settings are a convenience: a missing, unreadable or malformed file falls back
to defaults, and a failure to save is never fatal and never interrupts the user.
"""

from __future__ import annotations

import configparser
import json
import os
from pathlib import Path

APP_DIRECTORY = "kinetic-configurator"
LEGACY_APP_DIRECTORY = "kineticos-image-builder"


def _config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    base = Path(configured) if configured else Path.home() / ".config"
    return base.expanduser()


def config_root() -> Path:
    """Return the app's configuration folder."""
    return _config_home() / APP_DIRECTORY


def default_settings_path() -> Path:
    return config_root() / "settings.ini"


def legacy_settings_path() -> Path:
    """The JSON file used by earlier releases, read once for migration."""
    return _config_home() / LEGACY_APP_DIRECTORY / "settings.json"


def _restrict(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        # The folder may live on a filesystem without POSIX modes.
        pass


class Settings:
    """One settings.ini; a second constructor argument sets the path for tests."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_settings_path()
        self._parser = configparser.ConfigParser()
        # Preserve the exact key spelling used in the standard.
        self._parser.optionxform = str
        self._load()

    def _load(self) -> None:
        try:
            read = self._parser.read(self.path, encoding="utf-8")
        except (OSError, configparser.Error):
            self._parser = configparser.ConfigParser()
            self._parser.optionxform = str
            read = []
        if not read:
            self._migrate()

    def _migrate(self) -> None:
        """Import the checkout path from the old JSON settings file, once."""
        try:
            data = json.loads(legacy_settings_path().read_text())
        except (OSError, ValueError):
            return
        checkout = data.get("checkout_path") if isinstance(data, dict) else None
        if isinstance(checkout, str) and checkout:
            self._parser["project"] = {"checkout_path": checkout}

    def _get_bool(self, group: str, key: str, default: bool) -> bool:
        try:
            return self._parser.getboolean(group, key, fallback=default)
        except ValueError:
            return default

    def _set(self, group: str, key: str, value: str) -> None:
        if not self._parser.has_section(group):
            self._parser.add_section(group)
        self._parser.set(group, key, value)
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _restrict(self.path.parent)
            temporary = self.path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                self._parser.write(handle)
            os.replace(temporary, self.path)
        except OSError:
            return

    @property
    def system_title_bar(self) -> bool:
        return self._get_bool("window", "systemTitleBar", False)

    def set_system_title_bar(self, value: bool) -> None:
        self._set("window", "systemTitleBar", "true" if value else "false")

    @property
    def checkout_path(self) -> Path | None:
        raw = self._parser.get("project", "checkout_path", fallback=None)
        if not raw:
            return None
        return Path(raw).expanduser()

    def set_checkout_path(self, checkout: Path) -> None:
        self._set("project", "checkout_path", str(checkout.resolve()))
