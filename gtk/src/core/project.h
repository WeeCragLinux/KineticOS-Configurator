#pragma once

#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

// Reads and rewrites the KineticOS image project files. Edits are line based so the comments
// and layout in profile.yaml and modules/*.yaml survive; nothing is round-tripped through a
// YAML dumper. Port of the earlier Python configurator's project module.
namespace kineticos {

struct App {
    std::string name;
    std::string section;
    std::optional<std::pair<std::string, std::string>> repo;
    bool enabled{false};
};

struct Module {
    std::string name;
    std::string description;
    std::string path;
    std::vector<std::string> lines;
    std::vector<App> apps;
};

struct Selection {
    std::string baseImage;
    std::map<std::string, std::set<std::string>> apps;
    bool disableRpmfusion{false};
    bool disableBraveRepo{false};
    bool disableVivaldiRepo{false};
    bool braveRepoEnabled{false};
    bool vivaldiRepoEnabled{false};
    std::set<std::string> appModules;
    std::map<std::string, std::set<std::string>> removalApps;
    bool disableRemovals{false};

    // Every selected install package, excluding removals.
    std::set<std::string> chosen() const;
};

struct ProfileEntry {
    std::string name;
    bool enabled{false};
};

class Profile final {
public:
    explicit Profile(const std::string &root);

    const std::string &baseImage() const { return m_baseImage; }
    const std::vector<ProfileEntry> &entries() const { return m_entries; }

    // Keeps the baseline modules active, drops entries whose module no longer exists, and
    // lists every discovered module disabled.
    void ensureModules(const std::set<std::string> &moduleNames);

    void save(const std::string &baseImage, const std::vector<ProfileEntry> &entries);

private:
    std::string m_path;
    std::vector<std::string> m_lines;
    std::string m_baseImage;
    std::size_t m_header{0};
    std::size_t m_end{0};
    std::vector<ProfileEntry> m_entries;
};

std::map<std::string, Module> loadModules(const std::string &root);

std::vector<std::string> questions(const Selection &selection);

std::vector<ProfileEntry> resolve(const Profile &profile, const Selection &selection);

bool repoCommandEnabled(const Module *module, const std::string &repo);

void setRepoCommand(Module &module, const std::string &repo, bool enabled);

void apply(const std::string &root, const Selection &selection,
           std::map<std::string, Module> &modules, Profile &profile);

// Runs `dcli-bootc gen`. Returns (ok, output).
std::pair<bool, std::string> generate(const std::string &root);

const std::string &defaultImage();
const std::vector<std::string> &baseImages();
const std::vector<std::string> &baselineModules();
const std::set<std::string> &rpmfusionApps();
const std::set<std::string> &browserRepoApps(const std::string &repo);
const std::string &browserRepoUrl(const std::string &repo);

} // namespace kineticos
