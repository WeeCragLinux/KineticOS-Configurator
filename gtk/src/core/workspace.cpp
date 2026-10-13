#include "core/workspace.h"

#include "core/process.h"
#include "core/project.h"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <glibmm/datetime.h>

// Port of source/configurator/core/workspace.py. The GitWorker thread is replaced by
// synchronous free functions; callers run them on a worker thread.
namespace kineticos {

const char *const kRepositoryUrl =
    "https://github.com/WeeCragLinux/kinetic-image-builder.git";
const char *const kProjectDirectory = "kinetic-image-builder";

namespace {

namespace fs = std::filesystem;

const std::regex sectionPattern(R"(^\s*([A-Za-z_]\w*):)");
const std::regex itemPattern(R"(^(\s*)(#\s*)?-\s+(\S+)(.*)$)");
const std::set<std::string> appSections = {"packages", "flatpaks", "local_rpms", "remove"};

struct Item {
    std::size_t index{0};
    std::string section;
    std::string indent;
    bool commented{false};
    std::string name;
    std::string tail;
};

std::string trim(const std::string &text)
{
    const char *whitespace = " \t\r\n\f\v";
    const auto first = text.find_first_not_of(whitespace);
    if (first == std::string::npos)
        return {};
    return text.substr(first, text.find_last_not_of(whitespace) - first + 1);
}

[[maybe_unused]] std::vector<std::string> splitLines(const std::string &text)
{
    std::vector<std::string> lines;
    std::string current;
    for (const char character : text) {
        if (character == '\n') {
            if (!current.empty() && current.back() == '\r')
                current.pop_back();
            lines.push_back(current);
            current.clear();
        } else {
            current += character;
        }
    }
    if (!current.empty() || (!text.empty() && text.back() != '\n')) {
        if (!current.empty() && current.back() == '\r')
            current.pop_back();
        lines.push_back(current);
    }
    return lines;
}

std::string joinLines(const std::vector<std::string> &lines)
{
    std::string output;
    for (std::size_t index = 0; index < lines.size(); ++index) {
        if (index != 0)
            output += '\n';
        output += lines[index];
    }
    output += '\n';
    return output;
}

[[maybe_unused]] std::string readFile(const std::string &path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file)
        throw std::runtime_error("Could not read " + path);
    std::ostringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

void writeFile(const std::string &path, const std::string &text)
{
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file)
        throw std::runtime_error("Could not write " + path);
    file << text;
}

// Local copy of the project module's line parser: the header does not expose it.
std::vector<Item> iterItems(const std::vector<std::string> &lines)
{
    std::vector<Item> items;
    std::string section;
    bool haveSection = false;
    for (std::size_t index = 0; index < lines.size(); ++index) {
        std::smatch match;
        if (std::regex_match(lines[index], match, sectionPattern)) {
            section = match[1].str();
            haveSection = true;
            continue;
        }
        if (haveSection && std::regex_match(lines[index], match, itemPattern)) {
            Item item;
            item.index = index;
            item.section = section;
            item.indent = match[1].str();
            item.commented = match[2].matched;
            item.name = match[3].str();
            item.tail = match[4].str();
            items.push_back(item);
        }
    }
    return items;
}

std::optional<std::string> listIndent(const std::vector<std::string> &lines,
                                      const std::string &section)
{
    for (const Item &item : iterItems(lines)) {
        if (item.section == section && !item.commented)
            return item.indent;
    }
    return std::nullopt;
}

void setItem(std::vector<std::string> &lines, const std::string &section,
             const std::string &name, bool enabled)
{
    for (const Item &item : iterItems(lines)) {
        if (item.section != section || item.name != name)
            continue;
        if (!item.commented == enabled)
            return;
        std::string indent = item.indent;
        if (enabled) {
            if (const auto found = listIndent(lines, section))
                indent = *found;
        }
        const std::string marker = enabled ? "- " : "#- ";
        lines[item.index] = indent + marker + name + item.tail;
        return;
    }
}

std::string commandOutput(const ProcessResult &result)
{
    return trim(result.output);
}

GitResult replaceWithFreshClone(const std::string &path, const std::string &operation,
                                const ProjectChoices *choices);

} // namespace

std::string normalizedRemote(const std::string &url)
{
    std::string value = trim(url);
    while (!value.empty() && value.back() == '/')
        value.pop_back();
    if (value.size() >= 4 && value.compare(value.size() - 4, 4, ".git") == 0)
        value.erase(value.size() - 4);
    while (!value.empty() && value.back() == '/')
        value.pop_back();
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value;
}

bool isProject(const std::string &path)
{
    std::error_code error;
    return fs::is_regular_file(fs::path(path) / "profile.yaml", error)
        && fs::is_directory(fs::path(path) / "modules", error);
}

bool isOurCheckout(const std::string &path)
{
    if (!isProject(path))
        return false;

    ProcessResult remote =
        runProcess({"git", "-C", path, "config", "--get", "remote.origin.url"});
    if (!remote.started || remote.status != 0) {
        const fs::path configFile = fs::path(path) / ".git" / "config";
        std::error_code error;
        if (!fs::is_regular_file(configFile, error))
            return false;
        remote = runProcess(
            {"git", "config", "--file", configFile.string(), "--get", "remote.origin.url"});
    }
    return remote.started && remote.status == 0
        && normalizedRemote(trim(remote.output)) == normalizedRemote(kRepositoryUrl);
}

std::optional<ProjectChoices> captureProjectChoices(const std::string &root)
{
    const Profile profile(root);
    ProjectChoices choices;
    choices.baseImage = profile.baseImage();
    for (const ProfileEntry &entry : profile.entries())
        choices.modules[entry.name] = entry.enabled;

    for (const auto &moduleEntry : loadModules(root)) {
        const std::string &name = moduleEntry.first;
        const Module &module = moduleEntry.second;
        for (const App &app : module.apps)
            choices.apps[name][app.name] = app.enabled;

        std::map<std::pair<std::string, std::string>, bool> entries;
        for (const Item &item : iterItems(module.lines)) {
            if (item.section == "scripts")
                continue;
            entries[{item.section, item.name}] = !item.commented;
        }
        choices.listEntries[name] = entries;
    }
    return choices;
}

void reapplyProjectChoices(const std::string &root, const ProjectChoices &choices)
{
    Profile profile(root);
    const std::string baseImage =
        choices.baseImage.empty() ? profile.baseImage() : choices.baseImage;
    if (baseImage.empty())
        throw std::runtime_error(
            "Neither the saved project nor the upstream profile has a base image.");

    std::vector<ProfileEntry> moduleEntries;
    for (const ProfileEntry &entry : profile.entries()) {
        const auto saved = choices.modules.find(entry.name);
        moduleEntries.push_back(
            {entry.name, saved != choices.modules.end() ? saved->second : entry.enabled});
    }
    profile.save(baseImage, moduleEntries);

    for (auto &moduleEntry : loadModules(root)) {
        const std::string &moduleName = moduleEntry.first;
        Module &module = moduleEntry.second;

        std::map<std::string, bool> savedApps;
        const auto savedAppsFound = choices.apps.find(moduleName);
        if (savedAppsFound != choices.apps.end())
            savedApps = savedAppsFound->second;

        std::map<std::pair<std::string, std::string>, bool> savedEntries;
        const auto savedEntriesFound = choices.listEntries.find(moduleName);
        if (savedEntriesFound != choices.listEntries.end())
            savedEntries = savedEntriesFound->second;

        std::vector<std::string> lines = module.lines;
        for (const Item &item : iterItems(lines)) {
            if (item.section == "scripts")
                continue;

            std::optional<bool> enabled;
            if (appSections.count(item.section) != 0) {
                const auto found = savedApps.find(item.name);
                if (found != savedApps.end())
                    enabled = found->second;
            } else {
                const auto found = savedEntries.find({item.section, item.name});
                if (found != savedEntries.end())
                    enabled = found->second;
            }
            if (enabled)
                setItem(lines, item.section, item.name, *enabled);
        }
        if (lines != module.lines)
            writeFile(module.path, joinLines(lines));
    }
}

std::string backupPath(const std::string &checkout, const std::string &operation)
{
    const fs::path checkoutPath(checkout);
    const std::string timestamp = Glib::DateTime::create_now_local().format("%Y%m%d-%H%M%S");
    const std::string base = checkoutPath.filename().string() + "." + operation + "-backup-"
        + timestamp;
    fs::path backup = checkoutPath.parent_path() / base;
    std::error_code error;
    int suffix = 1;
    while (fs::exists(backup, error)) {
        backup = checkoutPath.parent_path() / (base + "-" + std::to_string(suffix));
        ++suffix;
    }
    return backup.string();
}

GitResult cloneProject(const std::string &path)
{
    if (!programOnPath("git"))
        return {false, "Git is not installed or is not on PATH.", ""};

    std::error_code error;
    if (fs::exists(path, error)) {
        if (isProject(path))
            return {true, "Opened the existing image project.", path};
        return {false,
                "The destination already exists and is not an image project:\n" + path
                    + "\n\nChoose another folder or open the existing project directly.",
                ""};
    }

    const ProcessResult result =
        runProcess({"git", "clone", "--progress", kRepositoryUrl, path});
    if (result.started && result.status == 0 && isProject(path))
        return {true, "Image project cloned successfully.", path};

    const std::string detail = commandOutput(result);
    return {false,
            detail.empty() ? "Git clone failed or the downloaded project is incomplete."
                           : detail,
            ""};
}

GitResult updateProject(const std::string &path)
{
    if (!isOurCheckout(path))
        return {false,
                "This project is not a clone of the expected image-builder repository. No "
                "changes were made.",
                ""};

    try {
        const auto choices = captureProjectChoices(path);
        if (!choices)
            return {false, "Could not read the current image project.", ""};
        return replaceWithFreshClone(path, "update", &*choices);
    } catch (const std::exception &error) {
        return {false, error.what(), ""};
    }
}

GitResult resetProject(const std::string &path)
{
    return replaceWithFreshClone(path, "reset", nullptr);
}

namespace {

GitResult replaceWithFreshClone(const std::string &path, const std::string &operation,
                                const ProjectChoices *choices)
{
    if (!isOurCheckout(path))
        return {false,
                "This project is not a clone of the expected image-builder repository. No "
                "changes were made.",
                ""};

    std::error_code error;
    fs::path checkout = fs::absolute(fs::path(path), error);
    if (error)
        checkout = fs::path(path);
    const fs::path resolved = fs::weakly_canonical(checkout, error);
    if (!error)
        checkout = resolved;
    if (!fs::is_directory(checkout, error)) {
        return {false,
                "The selected project folder no longer exists:\n" + checkout.string(),
                ""};
    }

    const fs::path parent = checkout.parent_path();
    const std::string stamp = Glib::DateTime::create_now_local().format("%Y%m%d-%H%M%S");
    const std::string prefix = "." + checkout.filename().string() + "." + operation + "-";
    fs::path temporary = parent / (prefix + stamp);
    int suffix = 1;
    while (fs::exists(temporary, error)) {
        temporary = parent / (prefix + stamp + "-" + std::to_string(suffix));
        ++suffix;
    }
    fs::create_directory(temporary, error);
    if (error) {
        return {false,
                "Could not create a temporary folder beside the project: " + error.message(),
                ""};
    }

    struct Cleanup {
        fs::path path;
        ~Cleanup()
        {
            std::error_code ignored;
            fs::remove_all(path, ignored);
        }
    } cleanup{temporary};

    const fs::path staged = temporary / checkout.filename();
    const ProcessResult cloned =
        runProcess({"git", "clone", "--progress", kRepositoryUrl, staged.string()});
    if (!cloned.started || cloned.status != 0) {
        const std::string detail = commandOutput(cloned);
        return {false, detail.empty() ? "Could not clone a fresh image project." : detail, ""};
    }
    if (!isOurCheckout(staged.string())) {
        return {false,
                "The downloaded folder is not a valid clone of the expected repository. The "
                "selected project was left untouched.",
                ""};
    }

    if (choices != nullptr) {
        try {
            reapplyProjectChoices(staged.string(), *choices);
        } catch (const std::exception &error) {
            return {false, error.what(), ""};
        }
    }

    const fs::path backup = backupPath(checkout.string(), operation);
    fs::rename(checkout, backup, error);
    if (error)
        return {false, "Could not move the existing project aside: " + error.message(), ""};

    fs::rename(staged, checkout, error);
    if (error) {
        const std::string installMessage = error.message();
        std::error_code restoreError;
        fs::rename(backup, checkout, restoreError);
        if (restoreError) {
            return {false,
                    "Could not install the fresh clone (" + installMessage
                        + "). The previous project remains at " + backup.string()
                        + "; automatic restore also failed (" + restoreError.message() + ").",
                    ""};
        }
        return {false,
                "Could not install the fresh clone (" + installMessage
                    + "); the previous project was restored.",
                ""};
    }

    std::string detail;
    if (operation == "update") {
        detail = "The project was updated from a fresh upstream clone. Existing base-image, "
                 "module, app, and list-item choices were reapplied where matching entries "
                 "remain. New entries use upstream defaults.\n\n";
    } else {
        detail = "The project was reset to a fresh upstream clone.\n\n";
    }
    detail += "The previous folder was saved at:\n" + backup.string();
    return {true, detail, checkout.string()};
}

} // namespace

} // namespace kineticos
