#pragma once

#include <map>
#include <optional>
#include <string>
#include <utility>

// Clone, select, and update the user's writable image project. Port of the earlier Python
// configurator's workspace module. The git operations are synchronous; callers run them on
// a worker thread and hand results back through a dispatcher.
namespace kineticos {

struct ProjectChoices {
    std::string baseImage;
    std::map<std::string, bool> modules;
    std::map<std::string, std::map<std::string, bool>> apps;
    std::map<std::string, std::map<std::pair<std::string, std::string>, bool>> listEntries;
};

struct GitResult {
    bool ok{false};
    std::string detail;
    std::string checkout;
};

extern const char *const kRepositoryUrl;
extern const char *const kProjectDirectory;

std::string normalizedRemote(const std::string &url);

bool isProject(const std::string &path);

bool isOurCheckout(const std::string &path);

// Reads the current image choices without consulting the checkout's git database.
std::optional<ProjectChoices> captureProjectChoices(const std::string &root);

// Reapplies saved module/app states to matching entries in a fresh template.
void reapplyProjectChoices(const std::string &root, const ProjectChoices &choices);

std::string backupPath(const std::string &checkout, const std::string &operation);

GitResult cloneProject(const std::string &path);
GitResult updateProject(const std::string &path);
GitResult resetProject(const std::string &path);

} // namespace kineticos
