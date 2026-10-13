#pragma once

#include <map>
#include <string>

// Merges upstream module entries without overwriting local configuration. Port of the
// earlier Python configurator's template_sync module.
namespace kineticos::template_sync {

struct SyncSummary {
    int added{0};
    int removed{0};
    int retained{0};

    void include(const SyncSummary &other);
};

// Imports only upstream-added/removed module names; keeps local states.
std::pair<std::string, SyncSummary> mergeProfileEntries(const std::string &baseText,
                                                        const std::string &localText,
                                                        const std::string &upstreamText);

// Merges list additions/removals while leaving existing local lines intact.
std::pair<std::string, SyncSummary> mergeModuleEntries(const std::string &baseText,
                                                       const std::string &localText,
                                                       const std::string &upstreamText);

// Applies an add/remove-only template sync to profile.yaml and modules/*.yaml.
SyncSummary mergeProjectEntries(const std::string &root,
                                const std::map<std::string, std::string> &baseFiles,
                                const std::map<std::string, std::string> &upstreamFiles);

} // namespace kineticos::template_sync
