"""Pure theming helpers.

Everything here works on plain RGB tuples and text so it can be tested without
a display. `ui/themewatcher.py` supplies the colours from the running Qt palette
and turns the results into a stylesheet.

The GTK standard expresses derived colours with CSS `color-mix()`; Qt style
sheets have no such function, so the mixes are computed here and substituted
into `assets/style.qss` at runtime.
"""

from __future__ import annotations

import re

# Fixed status colours from the standard (light and dark variants).
STATUS_COLORS: dict[str, dict[str, str]] = {
    "positive": {"light": "#067647", "dark": "#47cd89"},
    "neutral": {"light": "#a15c07", "dark": "#fdb022"},
    "negative": {"light": "#b42318", "dark": "#f97066"},
}

# Relative luminance at or below this value counts as a dark background.
DARK_LUMINANCE = 0.5

_DEFINE_COLOR_RE = re.compile(r"@define-color\s+([A-Za-z_][\w-]*)\s+([^;]+);")
_IMPORT_RE = re.compile(r"@import\s+(?:url\()?[\"']?([^\"')\s]+)[\"']?\)?\s*;")


def parse_gtk_defines(text: str) -> dict[str, str]:
    """Read `@define-color name value;` entries from a GTK stylesheet."""
    return {name: value.strip() for name, value in _DEFINE_COLOR_RE.findall(text)}


def parse_gtk_imports(text: str, base_dir) -> list:
    """Return local files referenced by `@import` in a GTK stylesheet."""
    from pathlib import Path

    imports = []
    for target in _IMPORT_RE.findall(text):
        if target.startswith(("http://", "https://", "data:")):
            continue
        imports.append((Path(base_dir) / target).expanduser())
    return imports


def parse_hex(value: str) -> tuple[int, int, int] | None:
    """Parse `#rgb`, `#rrggbb` or `#rrggbbaa` into an RGB tuple."""
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) not in (6, 8):
        return None
    try:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None
    return red, green, blue


def _linearize(channel: int) -> float:
    scaled = channel / 255.0
    if scaled <= 0.03928:
        return scaled / 12.92
    return ((scaled + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (_linearize(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def is_dark(rgb: tuple[int, int, int]) -> bool:
    return relative_luminance(rgb) < DARK_LUMINANCE


def as_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, channel)) for channel in rgb))


def mix(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
    percent: float,
) -> str:
    """Mix `percent` of `foreground` into `background`, in sRGB."""
    weight = max(0.0, min(100.0, percent)) / 100.0
    channels = (
        round(fg * weight + bg * (1.0 - weight))
        for fg, bg in zip(foreground, background)
    )
    return as_hex(tuple(channels))  # type: ignore[arg-type]


def derived_colors(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
) -> dict[str, str]:
    """The `kc_`-prefixed derived colours, with the standard's exact mixes."""
    return {
        "kc_fg": as_hex(foreground),
        "kc_bg": as_hex(background),
        "kc_surface": mix(foreground, background, 4),
        "kc_sunken": mix(foreground, background, 2),
        "kc_border": mix(foreground, background, 16),
        "kc_hover": mix(foreground, background, 8),
        "kc_muted": mix(foreground, background, 68),
        "kc_subtle": mix(foreground, background, 42),
    }


def status_colors(dark: bool) -> dict[str, str]:
    variant = "dark" if dark else "light"
    return {name: values[variant] for name, values in STATUS_COLORS.items()}


def substitute(template: str, colors: dict[str, str]) -> str:
    """Replace `$token` placeholders in a stylesheet template."""
    result = template
    for name, value in colors.items():
        result = result.replace(f"${name}", value)
    return result


def build_colors(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
    accent: tuple[int, int, int],
    accent_foreground: tuple[int, int, int],
) -> dict[str, str]:
    """All colours a stylesheet needs, including status variants."""
    dark = is_dark(background)
    colors = derived_colors(foreground, background)
    colors.update(
        {
            "kc_accent_bg": as_hex(accent),
            "kc_accent_fg": as_hex(accent_foreground),
            "kc_accent_hover": mix(foreground, accent, 15),
            "kc_selected": mix(accent, background, 22),
            "kc_dark": "true" if dark else "false",
        }
    )
    colors.update(status_colors(dark))
    for name, value in status_colors(dark).items():
        rgb = parse_hex(value) or (0, 0, 0)
        colors[f"kc_{name}"] = value
        colors[f"kc_{name}_border"] = mix(rgb, background, 45)
        colors[f"kc_{name}_bg"] = mix(rgb, background, 8)
    return colors
