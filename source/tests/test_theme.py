from __future__ import annotations

import unittest

from configurator.core import theme


class ThemeTests(unittest.TestCase):
    def test_parse_hex(self) -> None:
        self.assertEqual(theme.parse_hex("#fff"), (255, 255, 255))
        self.assertEqual(theme.parse_hex("#067647"), (6, 118, 71))
        self.assertEqual(theme.parse_hex("#06764780"), (6, 118, 71))
        self.assertIsNone(theme.parse_hex("not-a-colour"))

    def test_mix_uses_srgb_weights(self) -> None:
        self.assertEqual(theme.mix((255, 255, 255), (0, 0, 0), 50), "#808080")
        self.assertEqual(theme.mix((255, 255, 255), (0, 0, 0), 4), "#0a0a0a")

    def test_dark_detection(self) -> None:
        self.assertTrue(theme.is_dark((0, 0, 0)))
        self.assertFalse(theme.is_dark((255, 255, 255)))

    def test_derived_colors_use_the_standard_mixes(self) -> None:
        colors = theme.derived_colors((255, 255, 255), (0, 0, 0))
        self.assertEqual(colors["kc_surface"], theme.mix((255, 255, 255), (0, 0, 0), 4))
        self.assertEqual(colors["kc_border"], theme.mix((255, 255, 255), (0, 0, 0), 16))
        self.assertEqual(
            set(colors),
            {
                "kc_fg",
                "kc_bg",
                "kc_surface",
                "kc_sunken",
                "kc_border",
                "kc_hover",
                "kc_muted",
                "kc_subtle",
            },
        )

    def test_status_variants(self) -> None:
        self.assertEqual(theme.status_colors(False)["positive"], "#067647")
        self.assertEqual(theme.status_colors(True)["positive"], "#47cd89")
        self.assertEqual(theme.status_colors(True)["negative"], "#f97066")

    def test_build_colors_adds_status_and_selection(self) -> None:
        colors = theme.build_colors(
            (255, 255, 255), (0, 0, 0), (53, 132, 228), (255, 255, 255)
        )
        self.assertIn("kc_positive", colors)
        self.assertIn("kc_positive_border", colors)
        self.assertIn("kc_positive_bg", colors)
        self.assertIn("kc_selected", colors)
        self.assertEqual(colors["kc_dark"], "true")

    def test_parse_gtk_defines_and_imports(self) -> None:
        text = '@define-color window_bg_color #101010;\n@import "colors.css";'
        self.assertEqual(theme.parse_gtk_defines(text)["window_bg_color"], "#101010")
        imports = theme.parse_gtk_imports(text, "/tmp")
        self.assertEqual(len(imports), 1)
        self.assertEqual(str(imports[0]), "/tmp/colors.css")

    def test_substitute_replaces_tokens(self) -> None:
        self.assertEqual(theme.substitute("a $x b", {"x": "1"}), "a 1 b")


if __name__ == "__main__":
    unittest.main()
