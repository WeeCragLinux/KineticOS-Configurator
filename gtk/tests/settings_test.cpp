#include "core/settings.h"

#include <glib.h>

#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>

namespace {

namespace fs = std::filesystem;

std::string makeDir()
{
    char *path = g_dir_make_tmp("kc-settings-XXXXXX", nullptr);
    g_assert_nonnull(path);
    std::string directory(path);
    g_free(path);
    return directory;
}

std::string readFile(const std::string &path)
{
    std::ifstream file(path, std::ios::binary);
    return std::string((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
}

void testDefaultsWhenMissing()
{
    const std::string directory = makeDir();
    kineticos::Settings settings(directory + "/settings.ini");
    g_assert_false(settings.systemTitleBar());
    g_assert_true(settings.checkoutPath().empty());
    fs::remove_all(directory);
}

void testRoundTripAndImmediateSave()
{
    const std::string directory = makeDir();
    const std::string path = directory + "/settings.ini";
    kineticos::Settings settings(path);
    settings.setSystemTitleBar(true);
    settings.setCheckoutPath(directory + "/project");

    const std::string saved = readFile(path);
    g_assert_nonnull(std::strstr(saved.c_str(), "systemTitleBar"));

    kineticos::Settings reloaded(path);
    g_assert_true(reloaded.systemTitleBar());
    const std::string checkout = reloaded.checkoutPath();
    const std::string expected = directory + "/project";
    g_assert_cmpstr(checkout.c_str(), ==, expected.c_str());
    fs::remove_all(directory);
}

void testMalformedValueFallsBack()
{
    const std::string directory = makeDir();
    const std::string path = directory + "/settings.ini";
    {
        std::ofstream file(path);
        file << "[window]\nsystemTitleBar = not-a-bool\n";
    }
    kineticos::Settings settings(path);
    g_assert_false(settings.systemTitleBar());
    fs::remove_all(directory);
}

void testReadsLegacyCheckoutKey()
{
    const std::string directory = makeDir();
    const std::string path = directory + "/settings.ini";
    {
        std::ofstream file(path);
        file << "[project]\ncheckout_path = /tmp/old-project\n";
    }
    kineticos::Settings settings(path);
    const std::string checkout = settings.checkoutPath();
    g_assert_cmpstr(checkout.c_str(), ==, "/tmp/old-project");
    fs::remove_all(directory);
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/settings/defaults", testDefaultsWhenMissing);
    g_test_add_func("/settings/round-trip", testRoundTripAndImmediateSave);
    g_test_add_func("/settings/malformed", testMalformedValueFallsBack);
    g_test_add_func("/settings/legacy-key", testReadsLegacyCheckoutKey);
    return g_test_run();
}
