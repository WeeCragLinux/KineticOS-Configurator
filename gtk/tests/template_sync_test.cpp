#include "core/template_sync.h"

#include <glib.h>

#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>

namespace {

namespace fs = std::filesystem;

std::string makeDir()
{
    char *path = g_dir_make_tmp("kc-sync-XXXXXX", nullptr);
    g_assert_nonnull(path);
    std::string directory(path);
    g_free(path);
    return directory;
}

void writeFile(const fs::path &path, const std::string &text)
{
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file << text;
}

std::string readFile(const fs::path &path)
{
    std::ifstream file(path, std::ios::binary);
    return std::string((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
}

void testProfileMerge()
{
    const std::string base =
        "base_image: upstream\nenabled_modules:\n- base\n- apps\n- obsolete\n";
    const std::string local =
        "base_image: user-choice\nenabled_modules:\n- base\n#- apps\n- obsolete\n";
    const std::string upstream =
        "base_image: changed-upstream\nenabled_modules:\n- base\n- apps\n#- newly-added\n";

    const auto [merged, summary] =
        kineticos::template_sync::mergeProfileEntries(base, local, upstream);
    g_assert_nonnull(std::strstr(merged.c_str(), "base_image: user-choice"));
    g_assert_nonnull(std::strstr(merged.c_str(), "#- apps"));
    g_assert_nonnull(std::strstr(merged.c_str(), "#- newly-added"));
    g_assert_null(std::strstr(merged.c_str(), "obsolete"));
    g_assert_cmpint(summary.added, ==, 1);
    g_assert_cmpint(summary.removed, ==, 1);
}

void testModuleMerge()
{
    const std::string base =
        "description: original\npackages:\n  - stay\n  - remove-upstream\n  - user-kept\n"
        "flatpaks: []\n";
    const std::string local =
        "description: user-edited\npackages:\n  #- stay\n  - remove-upstream\n  #- user-kept\n"
        "flatpaks: []\n";
    const std::string upstream =
        "description: updated upstream\npackages:\n  - stay # upstream changed this existing entry\n"
        "  - new-package\nflatpaks:\n  - new-flatpak\nlocal_rpms:\n  - new-rpm\n";

    const auto [merged, summary] =
        kineticos::template_sync::mergeModuleEntries(base, local, upstream);
    g_assert_nonnull(std::strstr(merged.c_str(), "description: user-edited"));
    g_assert_nonnull(std::strstr(merged.c_str(), "  #- stay"));
    g_assert_null(std::strstr(merged.c_str(), "remove-upstream"));
    g_assert_nonnull(std::strstr(merged.c_str(), "  #- user-kept"));
    g_assert_nonnull(std::strstr(merged.c_str(), "  - new-package"));
    g_assert_nonnull(std::strstr(merged.c_str(), "  - new-flatpak"));
    g_assert_nonnull(std::strstr(merged.c_str(), "local_rpms:"));
    g_assert_nonnull(std::strstr(merged.c_str(), "  - new-rpm"));
    g_assert_cmpint(summary.added, ==, 3);
    g_assert_cmpint(summary.removed, ==, 1);
    g_assert_cmpint(summary.retained, ==, 1);
}

void testProjectMergeKeepsLocallyToggledModule()
{
    const std::string directory = makeDir();
    const fs::path root = directory;
    fs::create_directories(root / "modules");
    writeFile(root / "profile.yaml", "enabled_modules:\n- base\n#- old-module\n");
    writeFile(root / "modules" / "old-module.yaml", "description: old module\npackages: []\n");

    const std::map<std::string, std::string> base = {
        {"profile.yaml", "enabled_modules:\n- base\n- old-module\n"},
        {"modules/old-module.yaml", "description: old module\npackages: []\n"},
    };
    const std::map<std::string, std::string> upstream = {
        {"profile.yaml", "enabled_modules:\n- base\n"},
    };

    const auto summary =
        kineticos::template_sync::mergeProjectEntries(root.string(), base, upstream);
    g_assert_true(fs::exists(root / "modules" / "old-module.yaml"));
    g_assert_nonnull(
        std::strstr(readFile(root / "profile.yaml").c_str(), "#- old-module"));
    g_assert_cmpint(summary.retained, ==, 2);
    fs::remove_all(root);
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/template-sync/profile", testProfileMerge);
    g_test_add_func("/template-sync/module", testModuleMerge);
    g_test_add_func("/template-sync/project", testProjectMergeKeepsLocallyToggledModule);
    return g_test_run();
}
