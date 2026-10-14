#include "core/dcli.h"

#include <algorithm>
#include <cctype>
#include <initializer_list>

namespace kineticos {

namespace {

std::string lowercase(const std::string &text)
{
    std::string result = text;
    std::transform(result.begin(), result.end(), result.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return result;
}

bool containsAny(const std::string &haystack, std::initializer_list<const char *> markers)
{
    return std::any_of(markers.begin(), markers.end(), [&haystack](const char *marker) {
        return haystack.find(marker) != std::string::npos;
    });
}

} // namespace

bool buildReportedIdenticalImage(const std::string &buildOutput)
{
    return containsAny(lowercase(buildOutput),
                       {"this image is identical to the currently booted deployment"});
}

bool switchReportedNothingStaged(const std::string &switchOutput)
{
    return containsAny(lowercase(switchOutput),
                       {"matches the booted one", "already the tracked boot image",
                        "nothing will change on next boot"});
}

} // namespace kineticos
