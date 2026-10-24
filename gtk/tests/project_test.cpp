#include "core/project.h"

#include <glib.h>

#include <cstring>
#include <filesystem>
#include <fstream>
#include <set>
#include <string>
#include <vector>

namespace {

namespace fs = std::filesystem;

std::string makeRoot()
{
    char *path = g_dir_make_tmp("kc-project-XXXXXX", nullptr);
    g_assert_nonnull(path);
    std::string root(path);
    g_free(path);
    return root;
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

void makeProject(const fs::path &root, const bool appEnabled = false)
{
    fs::create_directories(root / "modules");
    writeFile(root / "profile.yaml",
              "base_image: ghcr.io/theblack-don/kineticos:default\n"
              "enabled_modules:\n"
              "- base\n"
              "- rpmfusion\n"
              "- extras\n"
              + std::string(appEnabled ? "- apps\n" : "#- apps\n"));
    writeFile(root / "modules" / "base.yaml", "description: base\npackages: []\n");
    writeFile(root / "modules" / "rpmfusion.yaml", "description: RPM Fusion repos\npackages: []\n");
    writeFile(root / "modules" / "extras.yaml", "description: Extras\npackages: []\n");
    writeFile(root / "modules" / "apps.yaml", "description: apps\npackages:\n  #- sample-app\n");
}

bool enabledOf(const std::vector<kineticos::ProfileEntry> &entries, const std::string &name)
{
    for (const auto &entry : entries)
        if (entry.name == name)
            return entry.enabled;
    return false;
}

bool hasEntry(const std::vector<kineticos::ProfileEntry> &entries, const std::string &name)
{
    for (const auto &entry : entries)
        if (entry.name == name)
            return true;
    return false;
}

bool contains(const std::vector<std::string> &values, const std::string &name)
{
    for (const std::string &value : values)
        if (value == name)
            return true;
    return false;
}

void testReadsEnabledAndDisabledApps()
{
    const fs::path root = makeRoot();
    makeProject(root);
    kineticos::Profile profile(root.string());
    auto modules = kineticos::loadModules(root.string());
    g_assert_cmpstr(profile.baseImage().c_str(), ==, "ghcr.io/theblack-don/kineticos:default");
    g_assert_false(modules["apps"].apps.empty());
    g_assert_false(modules["apps"].apps[0].enabled);

    writeFile(root / "modules" / "apps.yaml", "description: apps\npackages:\n  - sample-app\n");
    modules = kineticos::loadModules(root.string());
    g_assert_true(modules["apps"].apps[0].enabled);
    fs::remove_all(root);
}

void testDisabledModuleEnabledOnlyWithApp()
{
    const fs::path root = makeRoot();
    makeProject(root);
    kineticos::Profile profile(root.string());
    auto modules = kineticos::loadModules(root.string());
    std::set<std::string> names;
    for (const auto &entry : modules)
        names.insert(entry.first);
    profile.ensureModules(names);

    kineticos::Selection selection;
    selection.appModules.insert("apps");
    auto resolved = kineticos::resolve(profile, selection);
    g_assert_false(enabledOf(resolved, "apps"));
    g_assert_true(enabledOf(resolved, "base"));
    g_assert_true(enabledOf(resolved, "rpmfusion"));
    g_assert_true(enabledOf(resolved, "extras"));
    g_assert_false(contains(kineticos::questions(selection), "terra"));

    selection.apps["apps"] = {"sample-app"};
    resolved = kineticos::resolve(profile, selection);
    g_assert_true(enabledOf(resolved, "apps"));
    fs::remove_all(root);
}

void testNewModulesAddedDisabledAndBaselineEnabled()
{
    const fs::path root = makeRoot();
    fs::create_directories(root / "modules");
    writeFile(root / "profile.yaml",
              "base_image: example\nenabled_modules:\n- base\n#- rpmfusion\n#- extras\n");
    kineticos::Profile profile(root.string());
    profile.ensureModules({"apps", "new-apps"});
    const auto &entries = profile.entries();
    g_assert_cmpuint(entries.size(), ==, 4);
    g_assert_true(enabledOf(entries, "rpmfusion"));
    g_assert_false(hasEntry(entries, "extras"));
    g_assert_false(enabledOf(entries, "apps"));
    g_assert_false(enabledOf(entries, "new-apps"));
    fs::remove_all(root);
}

void testProfileSavePreservesComments()
{
    const fs::path root = makeRoot();
    fs::create_directories(root / "modules");
    for (const char *name : {"base", "rpmfusion", "extras", "apps", "discovered"})
        writeFile(root / "modules" / (std::string(name) + ".yaml"),
                  "description: " + std::string(name) + "\npackages: []\n");
    writeFile(root / "profile.yaml",
              "# project comment\n"
              "base_image: old-image  # keep this note\n"
              "enabled_modules:\n"
              "- base # always on\n"
              "# explanatory comment stays in place\n"
              "#- rpmfusion # was disabled\n"
              "  # - extras # was disabled too\n"
              "- apps # app selection\n"
              "package_manager: dnf\n"
              "# end comment\n");
    kineticos::Profile profile(root.string());
    g_assert_cmpuint(profile.entries().size(), ==, 4);
    g_assert_true(enabledOf(profile.entries(), "base"));
    g_assert_false(enabledOf(profile.entries(), "rpmfusion"));
    g_assert_false(enabledOf(profile.entries(), "extras"));
    g_assert_true(enabledOf(profile.entries(), "apps"));

    profile.save("new-image", {{"base", true},
                               {"rpmfusion", true},
                               {"extras", false},
                               {"apps", false},
                               {"discovered", false}});
    const std::string saved = readFile(root / "profile.yaml");
    g_assert_nonnull(std::strstr(saved.c_str(), "# project comment\n"));
    g_assert_nonnull(std::strstr(saved.c_str(), "# explanatory comment stays in place\n"));
    g_assert_nonnull(std::strstr(saved.c_str(), "package_manager: dnf\n# end comment\n"));
    g_assert_nonnull(std::strstr(saved.c_str(), "base_image: new-image  # keep this note"));
    g_assert_nonnull(std::strstr(saved.c_str(), "- rpmfusion # was disabled"));
    g_assert_nonnull(std::strstr(saved.c_str(), "  # - extras # was disabled too"));
    g_assert_nonnull(std::strstr(saved.c_str(), "#- apps # app selection"));
    g_assert_nonnull(std::strstr(saved.c_str(), "#- discovered"));
    fs::remove_all(root);
}

void testBrowserAppsEnableRepoCommands()
{
    const fs::path root = makeRoot();
    fs::create_directories(root / "modules");
    writeFile(root / "profile.yaml",
              "base_image: ghcr.io/theblack-don/kineticos:default\n"
              "enabled_modules:\n- base\n- rpmfusion\n- extras\n#- browsers\n");
    writeFile(root / "modules" / "base.yaml", "description: base\npackages: []\n");
    writeFile(root / "modules" / "rpmfusion.yaml", "description: r\npackages: []\n");
    writeFile(root / "modules" / "extras.yaml", "description: e\npackages: []\n");
    writeFile(root / "modules" / "browsers.yaml",
              "description: browsers\n"
              "packages:\n"
              "  #- brave-browser\n"
              "  #- vivaldi-stable\n"
              "scripts:\n"
              "  pre: |\n"
              "    # dnf config-manager addrepo --from-repofile="
              "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo\n"
              "    # dnf config-manager addrepo --from-repofile="
              "https://repo.vivaldi.com/stable/vivaldi-fedora.repo\n");

    kineticos::Profile profile(root.string());
    auto modules = kineticos::loadModules(root.string());
    std::set<std::string> names;
    for (const auto &entry : modules)
        names.insert(entry.first);
    profile.ensureModules(names);

    kineticos::Selection selection;
    selection.baseImage = profile.baseImage();
    selection.appModules.insert("browsers");
    selection.apps["browsers"] = {"brave-origin", "brave-browser"};
    kineticos::apply(root.string(), selection, modules, profile);

    const std::string saved = readFile(root / "modules" / "browsers.yaml");
    g_assert_nonnull(std::strstr(saved.c_str(), "  - brave-browser"));
    g_assert_nonnull(std::strstr(
        saved.c_str(),
        "    dnf config-manager addrepo --from-repofile="
        "https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo"));
    g_assert_nonnull(std::strstr(
        saved.c_str(),
        "    # dnf config-manager addrepo --from-repofile="
        "https://repo.vivaldi.com/stable/vivaldi-fedora.repo"));
    fs::remove_all(root);
}

void testStaleModuleEntriesDropped()
{
    const fs::path root = makeRoot();
    makeProject(root);
    // The image template no longer ships Terra, but an old project can still list it.
    writeFile(root / "profile.yaml",
              "base_image: ghcr.io/theblack-don/kineticos:default\n"
              "enabled_modules:\n- base\n- rpmfusion\n- terra\n#- apps\n");
    kineticos::Profile profile(root.string());
    auto modules = kineticos::loadModules(root.string());
    std::set<std::string> names;
    for (const auto &entry : modules)
        names.insert(entry.first);
    profile.ensureModules(names);
    g_assert_false(hasEntry(profile.entries(), "terra"));

    kineticos::Selection selection;
    selection.baseImage = profile.baseImage();
    selection.appModules.insert("apps");
    kineticos::apply(root.string(), selection, modules, profile);

    const std::string saved = readFile(root / "profile.yaml");
    g_assert_null(std::strstr(saved.c_str(), "terra"));
    g_assert_nonnull(std::strstr(saved.c_str(), "- base"));
    g_assert_nonnull(std::strstr(saved.c_str(), "- rpmfusion"));
    fs::remove_all(root);
}

void testRemovalsOptInAndDisable()
{
    const fs::path root = makeRoot();
    makeProject(root);
    writeFile(root / "profile.yaml", readFile(root / "profile.yaml") + "- removals\n");
    writeFile(root / "modules" / "removals.yaml",
              "description: optional package removals\n"
              "packages: []\n"
              "remove:\n"
              "  #- dolphin\n"
              "  #- spectacle\n");
    kineticos::Profile profile(root.string());
    auto modules = kineticos::loadModules(root.string());
    std::set<std::string> names;
    for (const auto &entry : modules)
        names.insert(entry.first);
    profile.ensureModules(names);

    kineticos::Selection selection;
    selection.baseImage = profile.baseImage();
    selection.appModules.insert("apps");
    selection.appModules.insert("removals");
    selection.removalApps["removals"] = {"dolphin", "spectacle"};

    // An enabled profile entry alone must not enable an empty removals module.
    g_assert_false(enabledOf(kineticos::resolve(profile, selection), "removals"));
    g_assert_false(contains(kineticos::questions(selection), "removals"));

    // Removals already enabled in the saved project still offer the opt-out.
    selection.apps["removals"] = {"dolphin"};
    g_assert_true(enabledOf(kineticos::resolve(profile, selection), "removals"));
    g_assert_true(contains(kineticos::questions(selection), "removals"));
    g_assert_cmpuint(selection.chosen().count("dolphin"), ==, 0);

    // Once the user edits the removals page, the opt-out is not offered and the choice is
    // applied even if a stale checkbox state says otherwise.
    selection.removalsEdited = true;
    selection.disableRemovals = true;
    g_assert_true(enabledOf(kineticos::resolve(profile, selection), "removals"));
    g_assert_false(contains(kineticos::questions(selection), "removals"));
    kineticos::apply(root.string(), selection, modules, profile);

    const std::string saved = readFile(root / "modules" / "removals.yaml");
    g_assert_nonnull(std::strstr(saved.c_str(), "  - dolphin\n"));
    g_assert_nonnull(std::strstr(saved.c_str(), "  #- spectacle\n"));
    const kineticos::Profile enabled(root.string());
    g_assert_true(enabledOf(enabled.entries(), "removals"));

    // Removals that came from the saved project can still be disabled at the end.
    selection.removalsEdited = false;
    kineticos::Profile reloaded(root.string());
    kineticos::apply(root.string(), selection, modules, reloaded);
    const kineticos::Profile disabled(root.string());
    g_assert_false(enabledOf(kineticos::resolve(disabled, selection), "removals"));
    g_assert_nonnull(
        std::strstr(readFile(root / "modules" / "removals.yaml").c_str(), "  #- dolphin\n"));
    g_assert_false(enabledOf(disabled.entries(), "removals"));
    fs::remove_all(root);
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/project/reads-apps", testReadsEnabledAndDisabledApps);
    g_test_add_func("/project/module-enable", testDisabledModuleEnabledOnlyWithApp);
    g_test_add_func("/project/ensure-modules", testNewModulesAddedDisabledAndBaselineEnabled);
    g_test_add_func("/project/profile-save", testProfileSavePreservesComments);
    g_test_add_func("/project/browser-repo", testBrowserAppsEnableRepoCommands);
    g_test_add_func("/project/stale-modules", testStaleModuleEntriesDropped);
    g_test_add_func("/project/removals", testRemovalsOptInAndDisable);
    return g_test_run();
}
