#include "core/process.h"
#include "core/workspace.h"

#include <glib.h>

#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>

namespace {

namespace fs = std::filesystem;

std::string makeDir()
{
    char *path = g_dir_make_tmp("kc-workspace-XXXXXX", nullptr);
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

void testNormalizedRemote()
{
    const std::string value = kineticos::normalizedRemote(
        " HTTPS://GitHub.com/WeeCragLinux/kinetic-image-builder.git/ ");
    g_assert_cmpstr(value.c_str(), ==,
                    "https://github.com/weecraglinux/kinetic-image-builder");
}

void testRecognizesProject()
{
    const std::string directory = makeDir();
    const fs::path project = fs::path(directory) / "image-project";
    fs::create_directories(project / "modules");
    writeFile(project / "profile.yaml", "name: test\n");
    g_assert_true(kineticos::isProject(project.string()));
    g_assert_false(kineticos::isProject(directory));
    fs::remove_all(directory);
}

void testBackupPathNamesOperation()
{
    const std::string path = kineticos::backupPath("/tmp/example-project", "reset");
    g_assert_nonnull(std::strstr(path.c_str(), "reset-backup-"));
    g_assert_nonnull(std::strstr(path.c_str(), "example-project"));
}

void testCaptureAndReapplyChoices()
{
    const std::string directory = makeDir();
    const fs::path root = directory;
    fs::create_directories(root / "modules");
    writeFile(root / "profile.yaml",
              "base_image: ghcr.io/example/default\n"
              "enabled_modules:\n- base\n#- apps\n");
    writeFile(root / "modules" / "base.yaml", "description: base\npackages: []\n");
    writeFile(root / "modules" / "apps.yaml",
              "description: apps\npackages:\n  #- sample-app\n");

    const auto choices = kineticos::captureProjectChoices(root.string());
    g_assert_true(choices.has_value());
    g_assert_cmpstr(choices->baseImage.c_str(), ==, "ghcr.io/example/default");

    // The user enables the app; a fresh template would carry it, but reapplying the saved
    // choices must restore the captured (disabled) state.
    writeFile(root / "modules" / "apps.yaml", "description: apps\npackages:\n  - sample-app\n");
    kineticos::reapplyProjectChoices(root.string(), *choices);

    const std::string apps = readFile(root / "modules" / "apps.yaml");
    g_assert_nonnull(std::strstr(apps.c_str(), "#- sample-app"));
    fs::remove_all(root);
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/workspace/normalized-remote", testNormalizedRemote);
    g_test_add_func("/workspace/is-project", testRecognizesProject);
    g_test_add_func("/workspace/backup-path", testBackupPathNamesOperation);
    g_test_add_func("/workspace/capture-reapply", testCaptureAndReapplyChoices);
    return g_test_run();
}
