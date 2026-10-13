"""Reads and rewrites the kineticos-plus project files.

Edits are line based so the comments and layout in profile.yaml and
modules/*.yaml survive. Nothing is round-tripped through a YAML dumper.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

BASE_IMAGES = (
    "ghcr.io/theblack-don/kineticos:default",
    "ghcr.io/theblack-don/kineticos:nvidia",
    "ghcr.io/theblack-don/kineticos:nvidia-legacy",
)

APP_SECTIONS = ("packages", "flatpaks", "local_rpms")
RPMFUSION_APPS = frozenset({"vlc", "mpv", "steam", "lutris", "discord"})
TERRA_APPS = frozenset({"terra-mangohud"})

# Apps that also need a line in their module's repos section turned on.
APP_REPOS = {
    "helium-bin": ("repos", "imput/helium"),
    "prismlauncher": ("repos", "g3tchoo/prismlauncher"),
}

SECTION_RE = re.compile(r"^([A-Za-z_]\w*):")
DESCRIPTION_RE = re.compile(r"^description:\s*(.*?)\s*$")
ITEM_RE = re.compile(r"^(\s*)(#\s*)?-\s+(\S+)(.*)$")
PROFILE_ITEM_RE = re.compile(r"^\s*(#\s*)?-\s*(\S+)\s*$")


@dataclass
class App:
    name: str
    section: str
    repo: tuple[str, str] | None
    enabled: bool = False


@dataclass
class Module:
    name: str
    description: str
    path: Path
    lines: list[str]
    apps: list[App]


@dataclass
class Selection:
    base_image: str | None = None
    apps: dict[str, set[str]] = field(default_factory=dict)
    disable_rpmfusion: bool = False
    disable_terra: bool = False
    originally_enabled_modules: set[str] = field(default_factory=set)

    def chosen(self) -> set[str]:
        return set().union(*self.apps.values())


def iter_items(lines: list[str]):
    section = None
    for index, line in enumerate(lines):
        header = SECTION_RE.match(line)
        if header:
            section = header.group(1)
            continue
        item = ITEM_RE.match(line)
        if item and section:
            yield index, section, item


def list_indent(lines: list[str], section: str) -> str | None:
    for _, found_section, item in iter_items(lines):
        if found_section == section and item.group(2) is None:
            return item.group(1)
    return None


def set_item(lines: list[str], section: str, name: str, enabled: bool) -> None:
    for index, found_section, item in iter_items(lines):
        if found_section == section and item.group(3) == name:
            if (item.group(2) is None) == enabled:
                return
            indent = item.group(1)
            if enabled:
                indent = list_indent(lines, section) or indent
            marker = "- " if enabled else "#- "
            lines[index] = f"{indent}{marker}{name}{item.group(4)}"
            return


def load_modules(root: Path) -> dict[str, Module]:
    modules = {}
    for path in sorted((root / "modules").glob("*.yaml")):
        lines = path.read_text().splitlines()
        description = next(
            (m.group(1) for m in map(DESCRIPTION_RE.match, lines) if m), ""
        )
        apps: list[App] = []
        for _, section, item in iter_items(lines):
            name = item.group(3)
            if section in APP_SECTIONS and name not in {a.name for a in apps}:
                apps.append(App(name, section, APP_REPOS.get(name), item.group(2) is None))
        modules[path.stem] = Module(path.stem, description, path, lines, apps)
    return modules


class Profile:
    def __init__(self, root: Path):
        self.path = root / "profile.yaml"
        self.lines = self.path.read_text().splitlines()
        self.base_image = next(
            (
                match.group(1)
                for line in self.lines
                if (match := re.match(r"^base_image:\s*(\S+)\s*$", line))
            ),
            None,
        )
        self.header = next(
            i for i, line in enumerate(self.lines) if line.startswith("enabled_modules:")
        )
        end = self.header + 1
        entries: list[tuple[str, bool]] = []
        while end < len(self.lines) and (m := PROFILE_ITEM_RE.match(self.lines[end])):
            entries.append((m.group(2), m.group(1) is None))
            end += 1
        self.end = end

        names = [name for name, _ in entries]
        if "terra" not in names:
            position = names.index("rpmfusion") + 1 if "rpmfusion" in names else len(entries)
            entries.insert(position, ("terra", False))
        self.entries = entries

    def save(self, base_image: str, entries: list[tuple[str, bool]]) -> None:
        lines = list(self.lines)
        lines[self.header + 1 : self.end] = [
            f"- {name}" if on else f"#- {name}" for name, on in entries
        ]
        lines = [
            f"base_image: {base_image}" if line.startswith("base_image:") else line
            for line in lines
        ]
        self.path.write_text("\n".join(lines) + "\n")


def questions(selection: Selection) -> list[str]:
    chosen = selection.chosen()
    asked = []
    if not chosen & RPMFUSION_APPS:
        asked.append("rpmfusion")
    if not chosen & TERRA_APPS:
        asked.append("terra")
    return asked


def resolve(profile: Profile, selection: Selection) -> list[tuple[str, bool]]:
    asked = questions(selection)
    result = []
    for name, _ in profile.entries:
        if name == "base":
            on = True
        elif name == "rpmfusion":
            on = not (selection.disable_rpmfusion and "rpmfusion" in asked)
        elif name == "terra":
            on = not (selection.disable_terra and "terra" in asked)
        else:
            on = bool(selection.apps.get(name))
        result.append((name, on))
    return result


def apply(
    root: Path,
    selection: Selection,
    modules: dict[str, Module],
    profile: Profile,
) -> None:
    entries = resolve(profile, selection)
    for name, on in entries:
        module = modules.get(name)
        if module is None or not module.apps:
            continue
        if not on and name not in selection.originally_enabled_modules:
            # Preserve configured packages in modules that were already disabled.
            continue
        chosen = selection.apps.get(name, set()) if on else set()
        lines = list(module.lines)
        for app in module.apps:
            wanted = app.name in chosen
            set_item(lines, app.section, app.name, wanted)
            if app.repo:
                set_item(lines, app.repo[0], app.repo[1], wanted)
        if lines != module.lines:
            module.path.write_text("\n".join(lines) + "\n")
    profile.save(selection.base_image, entries)


def generate(root: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["dcli-bootc", "gen", "-p", str(root)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "dcli-bootc was not found on PATH."
    return result.returncode == 0, (result.stdout + result.stderr).strip()
