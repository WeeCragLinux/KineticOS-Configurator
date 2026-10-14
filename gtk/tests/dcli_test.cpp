#include "core/dcli.h"

#include <glib.h>

#include <string>

namespace {

void testBuildReportsIdenticalImage()
{
    // Real dcli-bootc 0.6.0 output (colour codes are stripped when stdout is a pipe, but the
    // sentence itself survives either way).
    const std::string output =
        "Build complete\n"
        "  Image digest: sha256:abcd...\n"
        "\n! This image is identical to the currently booted deployment.\n"
        "\n  Switch skipped (--no-switch). Stage later with: dcli-bootc switch --tag default\n";
    g_assert_true(kineticos::buildReportedIdenticalImage(output));
}

void testBuildReportsIdenticalImageIsCaseInsensitive()
{
    g_assert_true(kineticos::buildReportedIdenticalImage(
        "THIS IMAGE IS IDENTICAL TO THE CURRENTLY BOOTED DEPLOYMENT."));
}

void testBuildWithoutMarkerIsNotEmpty()
{
    const std::string output =
        "Build complete\n"
        "  Image digest: sha256:abcd...\n"
        "\nVerified: 12 package(s) present, 0 removal(s) confirmed\n";
    g_assert_false(kineticos::buildReportedIdenticalImage(output));
    g_assert_false(kineticos::buildReportedIdenticalImage(""));
}

void testSwitchReportsMatchingDigest()
{
    const std::string output =
        "Switched\n"
        "\n! bootc staged a deployment, but its digest matches the booted one.\n"
        "    Nothing will change on next boot.\n"
        "\n  Nothing new to apply - skipping reboot.\n";
    g_assert_true(kineticos::switchReportedNothingStaged(output));
}

void testSwitchReportsAlreadyTrackedImage()
{
    const std::string output =
        "\n! No new deployment staged - localhost/image-builder:default is already the "
        "tracked boot image.\n"
        "    If you expected changes, the rebuilt image was identical to\n"
        "    the previous one (the build may not have picked up changes).\n";
    g_assert_true(kineticos::switchReportedNothingStaged(output));
}

void testSwitchThatStagedSomethingIsNotEmpty()
{
    const std::string output =
        "\nNew deployment staged:\n"
        "    localhost/image-builder:default  (sha256:1234...)\n"
        "    (booted was sha256:abcd...)\n";
    g_assert_false(kineticos::switchReportedNothingStaged(output));
    g_assert_false(kineticos::switchReportedNothingStaged(""));
}

} // namespace

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, nullptr);
    g_test_add_func("/dcli/build-identical", testBuildReportsIdenticalImage);
    g_test_add_func("/dcli/build-identical-case", testBuildReportsIdenticalImageIsCaseInsensitive);
    g_test_add_func("/dcli/build-not-identical", testBuildWithoutMarkerIsNotEmpty);
    g_test_add_func("/dcli/switch-matching-digest", testSwitchReportsMatchingDigest);
    g_test_add_func("/dcli/switch-already-tracked", testSwitchReportsAlreadyTrackedImage);
    g_test_add_func("/dcli/switch-staged", testSwitchThatStagedSomethingIsNotEmpty);
    return g_test_run();
}
