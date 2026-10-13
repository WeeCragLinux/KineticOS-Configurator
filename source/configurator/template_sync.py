"""Merge upstream module entries without overwriting local configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PROFILE_ITEM_RE = re.compile(r"^(\s*)(#\s*)?-\s*(\S+)\s*$")
ITEM_RE = re.compile(r"^(\s*)(#\s*)?-\s+(\S+)(.*)$")
HEADER_RE = re.compile(r"^(\s*)([A-Za-z_][\w-]*):(?:[ \t]*(.*))?$")


@dataclass(frozen=True)
class ListEntry:
    index: int
    path: tuple[str, ...]
    name: str
    line: str

    @property
    def key(self) -> tuple[tuple[str, ...], str]:
        return self.path, self.name


@dataclass(frozen=True)
class MappingHeader:
    index: int
    path: tuple[str, ...]
    indent: int
    line: str
    value: str


@dataclass
class SyncSummary:
    added: int = 0
    removed: int = 0
    retained: int = 0

    def include(self, other: SyncSummary) -> None:
        self.added += other.added
        self.removed += other.removed
        self.retained += other.retained


def _profile_block(lines: list[str]) -> tuple[int, int, dict[str, tuple[int, str]]]:
    header = next(
        (index for index, line in enumerate(lines) if line.startswith("enabled_modules:")),
        -1,
    )
    if header < 0:
        return -1, -1, {}

    end = header + 1
    entries: dict[str, tuple[int, str]] = {}
    while end < len(lines):
        match = PROFILE_ITEM_RE.match(lines[end])
        if not match:
            break
        entries.setdefault(match.group(3), (end, lines[end]))
        end += 1
    return header, end, entries


def _profile_row(text: str, name: str) -> str | None:
    _, _, entries = _profile_block(text.splitlines())
    item = entries.get(name)
    return item[1] if item else None


def merge_profile_entries(
    base_text: str, local_text: str, upstream_text: str
) -> tuple[str, SyncSummary]:
    """Import only upstream-added/removed module names; keep local states."""
    base_lines = base_text.splitlines()
    local_lines = local_text.splitlines()
    upstream_lines = upstream_text.splitlines()
    base_header, _, base_entries = _profile_block(base_lines)
    upstream_header, _, upstream_entries = _profile_block(upstream_lines)
    local_header, _, local_entries = _profile_block(local_lines)
    if min(base_header, upstream_header, local_header) < 0:
        raise ValueError("profile.yaml must contain an enabled_modules list.")
    summary = SyncSummary()

    # Remove an upstream-deleted module only when its local row is untouched.
    remove_indices = []
    for name in base_entries.keys() - upstream_entries.keys():
        current = local_entries.get(name)
        if current is None:
            continue
        if current[1] == base_entries[name][1]:
            remove_indices.append(current[0])
            summary.removed += 1
        else:
            summary.retained += 1
    for index in sorted(remove_indices, reverse=True):
        del local_lines[index]

    # New module rows inherit upstream's initial enabled/disabled state.
    _, _, local_entries = _profile_block(local_lines)
    upstream_rows = sorted(upstream_entries.items(), key=lambda item: item[1][0])
    for position, (name, (_, line)) in enumerate(upstream_rows):
        if name in base_entries or name in local_entries:
            continue

        # Place new modules near their upstream neighbors, without reordering
        # any rows that already belong to the user.
        _, local_end, local_entries = _profile_block(local_lines)
        insert_at = local_end
        for prior_name, _ in reversed(upstream_rows[:position]):
            prior = local_entries.get(prior_name)
            if prior is not None:
                insert_at = prior[0] + 1
                break
        else:
            for next_name, _ in upstream_rows[position + 1 :]:
                following = local_entries.get(next_name)
                if following is not None:
                    insert_at = following[0]
                    break
        local_lines.insert(insert_at, line)
        summary.added += 1

    return "\n".join(local_lines) + "\n", summary


def _parse_module_lines(
    lines: list[str],
) -> tuple[dict[tuple[tuple[str, ...], str], ListEntry], list[MappingHeader]]:
    stack: list[tuple[int, str]] = []
    entries: dict[tuple[tuple[str, ...], str], ListEntry] = {}
    headers: list[MappingHeader] = []

    for index, line in enumerate(lines):
        item = ITEM_RE.match(line)
        if item:
            path = tuple(key for _, key in stack)
            # Script bodies are arbitrary shell, not template list entries.
            if path and path[0] != "scripts":
                entry = ListEntry(index, path, item.group(3), line)
                entries.setdefault(entry.key, entry)
            continue

        header = HEADER_RE.match(line)
        if not header:
            continue
        indent = len(header.group(1).expandtabs(8))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, header.group(2)))
        headers.append(
            MappingHeader(
                index,
                tuple(key for _, key in stack),
                indent,
                line,
                header.group(3) or "",
            )
        )

    return entries, headers


def _header_paths(headers: list[MappingHeader]) -> set[tuple[str, ...]]:
    return {header.path for header in headers}


def _section_end(lines: list[str], header: MappingHeader) -> int:
    """Return the insertion point at the end of a mapping's YAML block."""
    _, headers = _parse_module_lines(lines)
    for candidate in headers:
        if candidate.index > header.index and candidate.indent <= header.indent:
            return candidate.index
    return len(lines)


def _header_block(
    lines: list[str], headers: list[MappingHeader], header: MappingHeader
) -> list[str]:
    end = len(lines)
    for candidate in headers:
        if candidate.index > header.index and candidate.indent <= header.indent:
            end = candidate.index
            break
    return lines[header.index:end]


def _append_new_headers(
    local_lines: list[str],
    base_headers: list[MappingHeader],
    upstream_lines: list[str],
    upstream_headers: list[MappingHeader],
) -> None:
    """Copy newly introduced list sections, but not locally removed sections."""
    base_paths = _header_paths(base_headers)
    upstream_entries, _ = _parse_module_lines(upstream_lines)
    _, local_headers = _parse_module_lines(local_lines)
    local_paths = _header_paths(local_headers)

    for header in upstream_headers:
        if header.path[0] == "scripts":
            continue
        if header.path in base_paths or header.path in local_paths:
            continue
        if not any(
            entry.path[: len(header.path)] == header.path
            for entry in upstream_entries.values()
        ):
            continue
        # If a previously existing parent was deleted locally, keep it deleted.
        prefixes = [header.path[:depth] for depth in range(1, len(header.path))]
        if any(prefix in base_paths and prefix not in local_paths for prefix in prefixes):
            continue

        block = _header_block(upstream_lines, upstream_headers, header)
        if len(header.path) == 1:
            if local_lines and local_lines[-1].strip():
                local_lines.append("")
            local_lines.extend(block)
        else:
            parent_path = header.path[:-1]
            parent = next(
                (item for item in local_headers if item.path == parent_path), None
            )
            if parent is None:
                continue
            insert_at = _section_end(local_lines, parent)
            local_lines[insert_at:insert_at] = block

        # Reparse after each copied block so nested headers are not duplicated.
        _, local_headers = _parse_module_lines(local_lines)
        local_paths = _header_paths(local_headers)


def _insert_entry(
    local_lines: list[str],
    entry: ListEntry,
    upstream_entries: dict[tuple[tuple[str, ...], str], ListEntry],
) -> bool:
    local_entries, local_headers = _parse_module_lines(local_lines)
    if entry.key in local_entries:
        return False

    siblings = sorted(
        (candidate for candidate in upstream_entries.values() if candidate.path == entry.path),
        key=lambda candidate: candidate.index,
    )
    sibling_position = next(
        index for index, candidate in enumerate(siblings) if candidate.key == entry.key
    )

    for previous in reversed(siblings[:sibling_position]):
        existing = local_entries.get(previous.key)
        if existing is not None:
            local_lines.insert(existing.index + 1, entry.line)
            return True
    for following in siblings[sibling_position + 1 :]:
        existing = local_entries.get(following.key)
        if existing is not None:
            local_lines.insert(existing.index, entry.line)
            return True

    header = next((item for item in local_headers if item.path == entry.path), None)
    if header is None:
        # A missing section present in the base was intentionally removed locally.
        return False
    if re.search(r"\[\s*\]", header.value):
        local_lines[header.index] = re.sub(r"\[\s*\]", "", header.line, count=1)
        local_lines.insert(header.index + 1, entry.line)
        return True

    local_lines.insert(_section_end(local_lines, header), entry.line)
    return True


def merge_module_entries(
    base_text: str, local_text: str, upstream_text: str
) -> tuple[str, SyncSummary]:
    """Merge list additions/removals while leaving existing local lines intact."""
    base_lines = base_text.splitlines()
    local_lines = local_text.splitlines()
    upstream_lines = upstream_text.splitlines()
    base_entries, base_headers = _parse_module_lines(base_lines)
    local_entries, _ = _parse_module_lines(local_lines)
    upstream_entries, upstream_headers = _parse_module_lines(upstream_lines)
    summary = SyncSummary()

    # Retain a removed item if the user changed its line (including its toggle).
    remove_indices = []
    for key in base_entries.keys() - upstream_entries.keys():
        current = local_entries.get(key)
        if current is None:
            continue
        if current.line == base_entries[key].line:
            remove_indices.append(current.index)
            summary.removed += 1
        else:
            summary.retained += 1
    for index in sorted(remove_indices, reverse=True):
        del local_lines[index]

    # Add newly introduced sections first, then entries in existing sections.
    _append_new_headers(
        local_lines, base_headers, upstream_lines, upstream_headers
    )

    for entry in sorted(upstream_entries.values(), key=lambda item: item.index):
        if entry.key in base_entries:
            continue
        current_entries, current_headers = _parse_module_lines(local_lines)
        if entry.key in current_entries:
            continue
        # Do not recreate a list section that was present in the base and
        # deliberately removed from the user's local file.
        current_paths = _header_paths(current_headers)
        base_paths = _header_paths(base_headers)
        if entry.path not in current_paths and entry.path in base_paths:
            continue
        _insert_entry(local_lines, entry, upstream_entries)

    final_entries, _ = _parse_module_lines(local_lines)
    summary.added = sum(
        1
        for key in upstream_entries.keys() - base_entries.keys()
        if key in final_entries and key not in local_entries
    )
    return "\n".join(local_lines) + "\n", summary


def merge_project_entries(
    root: Path,
    base_files: dict[str, str],
    upstream_files: dict[str, str],
) -> SyncSummary:
    """Apply an add/remove-only template sync to profile.yaml and modules/*.yaml."""
    summary = SyncSummary()
    profile_path = root / "profile.yaml"
    local_profile = profile_path.read_text()
    for label, content in (
        ("base", base_files["profile.yaml"]),
        ("local", local_profile),
        ("upstream", upstream_files["profile.yaml"]),
    ):
        if _profile_block(content.splitlines())[0] < 0:
            raise ValueError(f"The {label} profile.yaml has no enabled_modules list.")
    merged_profile, profile_summary = merge_profile_entries(
        base_files["profile.yaml"],
        local_profile,
        upstream_files["profile.yaml"],
    )
    if merged_profile != local_profile:
        profile_path.write_text(merged_profile)
    summary.include(profile_summary)

    module_names = {
        name.removeprefix("modules/")
        for name in set(base_files) | set(upstream_files)
        if name.startswith("modules/") and name.endswith(".yaml")
    }
    for name in sorted(module_names):
        relative = f"modules/{name}"
        path = root / relative
        base_text = base_files.get(relative)
        upstream_text = upstream_files.get(relative)
        local_text = path.read_text() if path.is_file() else None

        if base_text is None and upstream_text is not None:
            if local_text is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(upstream_text)
                summary.added += 1
            continue

        if upstream_text is None and base_text is not None:
            if local_text is None:
                continue
            module_name = Path(relative).stem
            profile_unchanged = _profile_row(
                local_profile, module_name
            ) == _profile_row(base_files["profile.yaml"], module_name)
            if local_text == base_text and profile_unchanged:
                path.unlink()
                summary.removed += 1
            else:
                summary.retained += 1
            continue

        if base_text is None or upstream_text is None or local_text is None:
            # A locally deleted module remains deleted; an unknown state is
            # safer to retain than to recreate or overwrite.
            continue

        merged, module_summary = merge_module_entries(
            base_text, local_text, upstream_text
        )
        if merged != local_text:
            path.write_text(merged)
        summary.include(module_summary)

    return summary
