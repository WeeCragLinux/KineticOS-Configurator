#include "core/theme.h"

#include <glib.h>

#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

namespace fs = std::filesystem;

std::string makeDir()
{
    char *path = g_dir_make_tmp("kc-theme-XXXXXX", nullptr);
    g_assert_nonnull(path);
    std::string directory(path);
    g_free(path);
    return directory;
}

void testLuminance()
{
    const auto black = kineticos::theme::luminance("#000000");
    const auto white = kineticos::theme::luminance("#ffffff");
    g_assert_true(black.has_value());
    g_assert_true(white.has_value());
    g_assert_cmpfloat(*black, <, 0.01);
    g_assert_cmpfloat(*white, >, 0.99);
    g_assert_false(kineticos::theme::luminance("not-a-colour").has_value());
}

void testIsDark()
{
    kineticos::theme::Colors colors;
    colors["window_bg_color"] = "#101010";
    g_assert_true(kineticos::theme::isDark(colors, false));
    colors["window_bg_color"] = "#fafafa";
    g_assert_false(kineticos::theme::isDark(colors, true));
    g_assert_true(kineticos::theme::isDark({}, true));
}

void testFontFamily()
{
    const std::string sans = kineticos::theme::fontFamily("Adwaita Sans Bold 11");
    const std::string mono = kineticos::theme::fontFamily("JetBrains Mono 12");
    g_assert_cmpstr(sans.c_str(), ==, "Adwaita Sans");
    g_assert_cmpstr(mono.c_str(), ==, "JetBrains Mono");
}

void testGtkCssPathsAndColors()
{
    const std::string directory = makeDir();
    fs::create_directories(fs::path(directory) / "gtk-4.0");
    {
        std::ofstream file(fs::path(directory) / "gtk-4.0" / "colors.css");
        file << "@define-color window_bg_color #101010;\n"
                "@define-color accent_bg_color #3584e4;\n";
    }
    {
        std::ofstream file(fs::path(directory) / "gtk-4.0" / "gtk.css");
        file << "@import \"colors.css\";\n"
                "@define-color window_fg_color @accent_bg_color;\n";
    }

    const std::vector<std::string> paths = kineticos::theme::gtkCssPaths(directory);
    g_assert_cmpuint(paths.size(), ==, 2);

    const kineticos::theme::Colors colors = kineticos::theme::gtkColors(paths);
    g_assert_cmpstr(colors.at("window_bg_color").c_str(), ==, "#101010");
    g_assert_cmpstr(colors.at("window_fg_color").c_str(), ==, "#3584e4");
    fs::remove_all(directory);
}

void testFontStylesheet()
{
    kineticos::theme::Theme theme;
    theme.monoFont = "JetBrains Mono";
    const std::string css = kineticos::theme::fontStylesheet(theme);
    g_assert_nonnull(g_strstr_len(css.c_str(), -1, ".mono"));
    g_assert_nonnull(g_strstr_len(css.c_str(), -1, "JetBrains Mono"));
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/theme/luminance", testLuminance);
    g_test_add_func("/theme/is-dark", testIsDark);
    g_test_add_func("/theme/font-family", testFontFamily);
    g_test_add_func("/theme/gtk-colors", testGtkCssPathsAndColors);
    g_test_add_func("/theme/font-stylesheet", testFontStylesheet);
    return g_test_run();
}
