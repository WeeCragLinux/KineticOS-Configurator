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
    "ghcr.io/theblack-don/kineticos:deck",
)

BASELINE_MODULES = ("base", "rpmfusion", "terra")

APP_SECTIONS = ("packages", "flatpaks", "local_rpms")
RPMFUSION_APPS = frozenset({"vlc", "mpv", "steam", "lutris", "discord"})
TERRA_APPS = frozenset({"terra-mangohud"})

# Apps that also need a line in their module's repos section turned on.
APP_REPOS = {
    "helium-bin": ("copr", "imput/helium"),
    "prismlauncher": ("copr", "g3tchoo/prismlauncher"),
}

BROWSER_REPO_URLS = {
    "brave": "brave-browser-rpm-release.s3.brave.com/brave-browser.repo",
    "vivaldi": "repo.vivaldi.com/stable/vivaldi-fedora.repo",
}
BROWSER_REPO_APPS = {
    "brave": frozenset({"brave-browser", "brave-origin"}),
    "vivaldi": frozenset({"vivaldi-stable"}),
}

SECTION_RE = re.compile(r"^\s*([A-Za-z_]\w*):")
DESCRIPTION_RE = re.compile(r"^description:\s*(.*?)\s*$")
ITEM_RE = re.compile(r"^(\s*)(#\s*)?-\s+(\S+)(.*)$")
PROFILE_HEADER_RE = re.compile(r"^\s*enabled_modules\s*:")
PROFILE_KEY_RE = re.compile(r"^[A-Za-z_]\w*\s*:")
PROFILE_ITEM_RE = re.compile(
    r"^(?P<indent>\s*)(?P<comment>#\s*)?(?P<dash>-\s*)"
    r"(?P<name>[^#\s]+)(?P<tail>.*)$"
)
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
REMOVED_PACKAGE_ERROR_RE = re.compile(r"^-\s+should have been removed:\s+(\S+)\s*$")


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
    disable_brave_repo: bool = False
    disable_vivaldi_repo: bool = False
    brave_repo_enabled: bool = False
    vivaldi_repo_enabled: bool = False
    app_modules: set[str] = field(default_factory=set)

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
                if (
                    match := re.match(
                        r"^\s*base_image\s*:\s*(\S+?)(?:\s+#.*)?\s*$", line
                    )
                )
            ),
            None,
        )
        try:
            self.header = next(
                i for i, line in enumerate(self.lines) if PROFILE_HEADER_RE.match(line)
            )
        except StopIteration as error:
            raise ValueError("profile.yaml must contain an enabled_modules list") from error

        end = self.header + 1
        while end < len(self.lines):
            if PROFILE_KEY_RE.match(self.lines[end]):
                break
            end += 1
        self.end = end
        entries: list[tuple[str, bool]] = []
        for line in self.lines[self.header + 1 : self.end]:
            match = PROFILE_ITEM_RE.match(line)
            if match:
                entries.append((match.group("name"), match.group("comment") is None))
        self.entries = entries

    def ensure_modules(self, module_names) -> None:
        """Keep baseline modules active and list every discovered module disabled."""
        states = dict(self.entries)
        ordered = [name for name, _ in self.entries]
        for index, name in enumerate(BASELINE_MODULES):
            if name not in states:
                states[name] = True
                ordered.insert(min(index, len(ordered)), name)
            else:
                states[name] = True
        for name in sorted(set(module_names) - set(ordered)):
            states[name] = False
            ordered.append(name)
        self.entries = [(name, states[name]) for name in ordered]

    def save(self, base_image: str, entries: list[tuple[str, bool]]) -> None:
        lines = list(self.lines)
        existing: dict[str, int] = {}
        for index in range(self.header + 1, self.end):
            match = PROFILE_ITEM_RE.match(lines[index])
            if match:
                existing.setdefault(match.group("name"), index)

        insertions: dict[int, list[str]] = {}
        for entry_index, (name, enabled) in enumerate(entries):
            line_index = existing.get(name)
            if line_index is None:
                next_index = next(
                    (
                        existing[next_name]
                        for next_name, _ in entries[entry_index + 1 :]
                        if next_name in existing
                    ),
                    None,
                )
                if next_index is not None:
                    line_index = next_index
                elif existing:
                    line_index = max(existing.values()) + 1
                else:
                    line_index = self.header + 1
                style_index = next(
                    (index for index in existing.values() if index == line_index),
                    max(existing.values()) if existing else None,
                )
                style = (
                    PROFILE_ITEM_RE.match(lines[style_index])
                    if style_index is not None
                    else None
                )
                indent = style.group("indent") if style else ""
                dash = style.group("dash") if style else "- "
                comment = "" if enabled else "#"
                insertions.setdefault(line_index, []).append(
                    f"{indent}{comment}{dash}{name}"
                )
                continue

            match = PROFILE_ITEM_RE.match(lines[line_index])
            if not match:
                continue
            currently_enabled = match.group("comment") is None
            if currently_enabled != enabled:
                marker = "" if enabled else "#"
                lines[line_index] = (
                    f"{match.group('indent')}{marker}{match.group('dash')}"
                    f"{match.group('name')}{match.group('tail')}"
                )

        output: list[str] = []
        for index, line in enumerate(lines):
            output.extend(insertions.get(index, ()))
            output.append(line)
        output.extend(insertions.get(len(lines), ()))

        base_re = re.compile(r"^(\s*base_image\s*:\s*)\S+(.*)$")
        for index, line in enumerate(output):
            match = base_re.match(line)
            if match:
                output[index] = f"{match.group(1)}{base_image}{match.group(2)}"
                break
        self.path.write_text("\n".join(output) + "\n")


def questions(selection: Selection) -> list[str]:
    chosen = selection.chosen()
    asked = []
    if not chosen & RPMFUSION_APPS:
        asked.append("rpmfusion")
    if not chosen & TERRA_APPS:
        asked.append("terra")
    if not chosen & BROWSER_REPO_APPS["brave"] and selection.brave_repo_enabled:
        asked.append("brave")
    if not chosen & BROWSER_REPO_APPS["vivaldi"] and selection.vivaldi_repo_enabled:
        asked.append("vivaldi")
    return asked


def resolve(profile: Profile, selection: Selection) -> list[tuple[str, bool]]:
    asked = questions(selection)
    result = []
    for name, was_enabled in profile.entries:
        if name == "base":
            on = True
        elif name == "rpmfusion":
            on = not (selection.disable_rpmfusion and "rpmfusion" in asked)
        elif name == "terra":
            on = not (selection.disable_terra and "terra" in asked)
        elif name in selection.app_modules:
            on = bool(selection.apps.get(name))
        else:
            on = was_enabled
        result.append((name, on))
    return result


def local_rpm_package_name(root: Path, entry: str) -> str | None:
    try:
        result = subprocess.run(
            ["rpm", "-qp", "--queryformat", "%{NAME}", str(root / "rpms" / entry)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def expected_package_state(
    modules: dict[str, Module],
    module_states: list[tuple[str, bool]],
    root: Path,
) -> tuple[set[str], set[str], set[str]]:
    """Return selected installs, effective removals, and remove/install overlaps.

    The image build runs its removals before later modules install apps. Only
    enabled modules contribute to the composed image, so selected installs
    cancel matching removals in the final expected package state.
    """
    selected_installs: set[str] = set()
    removed_packages: set[str] = set()

    for module_name, enabled in module_states:
        if not enabled:
            continue
        module = modules.get(module_name)
        if module is None:
            continue
        for _, section, item in iter_items(module.lines):
            if item.group(2) is not None:
                continue
            package = item.group(3)
            if section == "packages":
                selected_installs.add(package)
            elif section == "remove":
                removed_packages.add(package)
            elif section == "local_rpms":
                package_name = local_rpm_package_name(root, package)
                if package_name:
                    selected_installs.add(package_name)

    effective_removals = removed_packages - selected_installs
    reinstall_overlaps = removed_packages & selected_installs
    return selected_installs, effective_removals, reinstall_overlaps


def only_expected_removal_overlaps(output: str, reinstall_overlaps: set[str]) -> bool:
    """Recognize dcli-bootc's old verifier false-positive as the sole failure.

    A failed build is accepted only when dcli-bootc completed the image and its
    verification block contains exclusively removal warnings for packages that
    an enabled module installs later. Missing-package and removal-only errors
    remain failures.
    """
    clean_output = ANSI_ESCAPE_RE.sub("", output)
    build_complete = clean_output.find("Build complete")
    failure_header = clean_output.find("Image does not match your modules:")
    failure_footer = clean_output.find(
        "Fix the modules/repos and rebuild.", failure_header
    )
    if (
        build_complete < 0
        or failure_header < build_complete
        or failure_footer < 0
    ):
        return False

    errors = clean_output[failure_header + len("Image does not match your modules:") : failure_footer]
    reported_overlaps = []
    for line in errors.splitlines():
        line = line.strip()
        if not line:
            continue
        match = REMOVED_PACKAGE_ERROR_RE.fullmatch(line)
        if match is None or match.group(1) not in reinstall_overlaps:
            return False
        reported_overlaps.append(match.group(1))
    return bool(reported_overlaps)


def repo_command_enabled(module: Module | None, repo: str) -> bool:
    if module is None:
        return False
    marker = BROWSER_REPO_URLS[repo]
    for line in module.lines:
        if marker not in line or "dnf config-manager" not in line:
            continue
        return not line.lstrip().startswith("#")
    return False


def set_repo_command(module: Module, repo: str, enabled: bool) -> None:
    marker = BROWSER_REPO_URLS[repo]
    for index, line in enumerate(module.lines):
        if marker not in line or "dnf config-manager" not in line:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        command = line[len(indent) :]
        if command.startswith("#"):
            command = command[1:]
            if command.startswith(" "):
                command = command[1:]
        if enabled:
            module.lines[index] = indent + command
        else:
            module.lines[index] = indent + "# " + command
        return


def apply(
    root: Path,
    selection: Selection,
    modules: dict[str, Module],
    profile: Profile,
) -> None:
    entries = resolve(profile, selection)
    chosen_apps = selection.chosen()
    for name, on in entries:
        if name == "base":
            # Base is mandatory, not an app-selection module. Preserve its package list.
            continue
        module = modules.get(name)
        if module is None:
            continue
        if not module.apps:
            continue
        chosen = selection.apps.get(name, set()) if on else set()
        lines = list(module.lines)
        for app in module.apps:
            wanted = app.name in chosen
            set_item(lines, app.section, app.name, wanted)
            if app.repo:
                set_item(lines, app.repo[0], app.repo[1], wanted)
        module.lines = lines

    browser_module = modules.get("browsers")
    if browser_module is not None:
        brave_enabled = bool(chosen_apps & BROWSER_REPO_APPS["brave"]) or (
            selection.brave_repo_enabled and not selection.disable_brave_repo
        )
        vivaldi_enabled = bool(chosen_apps & BROWSER_REPO_APPS["vivaldi"]) or (
            selection.vivaldi_repo_enabled and not selection.disable_vivaldi_repo
        )
        set_repo_command(browser_module, "brave", brave_enabled)
        set_repo_command(browser_module, "vivaldi", vivaldi_enabled)

    for module in modules.values():
        if module.lines != module.path.read_text().splitlines():
            module.path.write_text("\n".join(module.lines) + "\n")
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
