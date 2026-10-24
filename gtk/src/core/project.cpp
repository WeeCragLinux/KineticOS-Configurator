#include "core/project.h"

#include "core/process.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

// Port of source/configurator/core/project.py. The line based parser is the
// specification, so the regular expressions below mirror the Python ones exactly.
namespace kineticos {

namespace {

namespace fs = std::filesystem;

const std::regex sectionPattern(R"(^\s*([A-Za-z_]\w*):)");
const std::regex descriptionPattern(R"(^description:\s*(.*?)\s*$)");
const std::regex itemPattern(R"(^(\s*)(#\s*)?-\s+(\S+)(.*)$)");
const std::regex profileHeaderPattern(R"(^\s*enabled_modules\s*:)");
const std::regex profileKeyPattern(R"(^[A-Za-z_]\w*\s*:)");
const std::regex profileItemPattern(R"(^(\s*)(#\s*)?(-\s*)([^#\s]+)(.*)$)");
const std::regex baseImagePattern(R"(^\s*base_image\s*:\s*(\S+?)(?:\s+#.*)?\s*$)");
const std::regex baseImageReplacePattern(R"(^(\s*base_image\s*:\s*)\S+(.*)$)");

const std::set<std::string> appSections = {"packages", "flatpaks", "local_rpms", "remove"};

const std::map<std::string, std::pair<std::string, std::string>> &appRepos()
{
    static const std::map<std::string, std::pair<std::string, std::string>> repos = {
        {"helium-bin", {"copr", "imput/helium"}},
        {"prismlauncher", {"copr", "g3tchoo/prismlauncher"}},
    };
    return repos;
}

// Mirrors Python str.splitlines() for the newline conventions used by these files.
std::vector<std::string> splitLines(const std::string &text)
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

std::string readFile(const std::string &path)
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

std::string trim(const std::string &text)
{
    const char *whitespace = " \t\r\n\f\v";
    const auto first = text.find_first_not_of(whitespace);
    if (first == std::string::npos)
        return {};
    return text.substr(first, text.find_last_not_of(whitespace) - first + 1);
}

bool intersects(const std::set<std::string> &left, const std::set<std::string> &right)
{
    for (const std::string &value : left) {
        if (right.count(value) != 0)
            return true;
    }
    return false;
}

// Removals loaded from the saved project can still be turned off at the end. Once the user
// edits a removals page, their choices are explicit and the opt-out is not offered again.
bool removalsAsked(const Selection &selection)
{
    if (selection.removalsEdited)
        return false;
    for (const auto &entry : selection.removalApps) {
        const auto selected = selection.apps.find(entry.first);
        if (selected != selection.apps.end() && intersects(selected->second, entry.second))
            return true;
    }
    return false;
}

struct Item {
    std::size_t index{0};
    std::string section;
    std::string indent;
    bool commented{false};
    std::string name;
    std::string tail;
};

// Port of iter_items(): yields list entries together with their enclosing section.
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

// Port of set_item(): toggles a list entry in place, keeping the existing layout.
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

} // namespace

const std::string &defaultImage()
{
    return baseImages().front();
}

const std::vector<std::string> &baseImages()
{
    static const std::vector<std::string> images = {
        "ghcr.io/theblack-don/kineticos:default",
        "ghcr.io/theblack-don/kineticos:nvidia",
        "ghcr.io/theblack-don/kineticos:nvidia-legacy",
        "ghcr.io/theblack-don/kineticos:deck",
    };
    return images;
}

const std::vector<std::string> &baselineModules()
{
    static const std::vector<std::string> modules = {"base", "rpmfusion"};
    return modules;
}

const std::set<std::string> &rpmfusionApps()
{
    static const std::set<std::string> apps = {"vlc", "mpv", "steam", "lutris", "discord"};
    return apps;
}

const std::set<std::string> &browserRepoApps(const std::string &repo)
{
    static const std::set<std::string> brave = {"brave-browser", "brave-origin"};
    static const std::set<std::string> vivaldi = {"vivaldi-stable"};
    static const std::set<std::string> empty;
    if (repo == "brave")
        return brave;
    if (repo == "vivaldi")
        return vivaldi;
    return empty;
}

const std::string &browserRepoUrl(const std::string &repo)
{
    static const std::string brave =
        "brave-browser-rpm-release.s3.brave.com/brave-browser.repo";
    static const std::string vivaldi = "repo.vivaldi.com/stable/vivaldi-fedora.repo";
    static const std::string empty;
    if (repo == "brave")
        return brave;
    if (repo == "vivaldi")
        return vivaldi;
    return empty;
}

std::set<std::string> Selection::chosen() const
{
    std::set<std::string> result;
    for (const auto &entry : apps) {
        const std::set<std::string> *removals = nullptr;
        const auto found = removalApps.find(entry.first);
        if (found != removalApps.end())
            removals = &found->second;
        for (const std::string &name : entry.second) {
            if (removals == nullptr || removals->count(name) == 0)
                result.insert(name);
        }
    }
    return result;
}

std::map<std::string, Module> loadModules(const std::string &root)
{
    std::map<std::string, Module> modules;
    std::vector<std::string> paths;
    std::error_code error;
    const fs::path directory = fs::path(root) / "modules";
    if (fs::is_directory(directory, error)) {
        for (const fs::directory_entry &entry : fs::directory_iterator(directory, error)) {
            if (!entry.is_regular_file(error))
                continue;
            const fs::path path = entry.path();
            if (path.extension() == ".yaml")
                paths.push_back(path.string());
        }
    }
    std::sort(paths.begin(), paths.end());

    for (const std::string &path : paths) {
        const std::vector<std::string> lines = splitLines(readFile(path));

        std::string description;
        for (const std::string &line : lines) {
            std::smatch match;
            if (std::regex_match(line, match, descriptionPattern)) {
                description = match[1].str();
                break;
            }
        }

        std::vector<App> apps;
        std::set<std::string> seen;
        for (const Item &item : iterItems(lines)) {
            if (appSections.count(item.section) == 0 || seen.count(item.name) != 0)
                continue;
            seen.insert(item.name);
            App app;
            app.name = item.name;
            app.section = item.section;
            const auto repo = appRepos().find(item.name);
            if (repo != appRepos().end())
                app.repo = repo->second;
            app.enabled = !item.commented;
            apps.push_back(app);
        }

        Module module;
        module.name = fs::path(path).stem().string();
        module.description = description;
        module.path = path;
        module.lines = lines;
        module.apps = apps;
        modules[module.name] = module;
    }
    return modules;
}

Profile::Profile(const std::string &root)
{
    m_path = (fs::path(root) / "profile.yaml").string();
    m_lines = splitLines(readFile(m_path));

    for (const std::string &line : m_lines) {
        std::smatch match;
        if (std::regex_match(line, match, baseImagePattern)) {
            m_baseImage = match[1].str();
            break;
        }
    }

    bool foundHeader = false;
    for (std::size_t index = 0; index < m_lines.size(); ++index) {
        if (std::regex_match(m_lines[index], profileHeaderPattern)) {
            m_header = index;
            foundHeader = true;
            break;
        }
    }
    if (!foundHeader)
        throw std::runtime_error("profile.yaml must contain an enabled_modules list");

    std::size_t end = m_header + 1;
    while (end < m_lines.size()) {
        if (std::regex_match(m_lines[end], profileKeyPattern))
            break;
        ++end;
    }
    m_end = end;

    for (std::size_t index = m_header + 1; index < m_end; ++index) {
        std::smatch match;
        if (std::regex_match(m_lines[index], match, profileItemPattern))
            m_entries.push_back({match[4].str(), !match[2].matched});
    }
}

void Profile::ensureModules(const std::set<std::string> &moduleNames)
{
    const std::vector<std::string> &baseline = baselineModules();
    std::map<std::string, bool> states;
    std::vector<std::string> ordered;
    for (const ProfileEntry &entry : m_entries) {
        // A module removed from the image template (for example Terra) can linger in an
        // existing profile.yaml. Drop the entry instead of offering a dangling module.
        const bool isBaseline =
            std::find(baseline.begin(), baseline.end(), entry.name) != baseline.end();
        if (!isBaseline && moduleNames.count(entry.name) == 0)
            continue;
        states[entry.name] = entry.enabled;
        ordered.push_back(entry.name);
    }

    std::size_t index = 0;
    for (const std::string &name : baselineModules()) {
        const auto found = states.find(name);
        if (found == states.end()) {
            states[name] = true;
            const std::size_t position = std::min(index, ordered.size());
            ordered.insert(ordered.begin() + static_cast<std::ptrdiff_t>(position), name);
        } else {
            found->second = true;
        }
        ++index;
    }

    const std::set<std::string> alreadyOrdered(ordered.begin(), ordered.end());
    for (const std::string &name : moduleNames) {
        if (alreadyOrdered.count(name) != 0)
            continue;
        states[name] = false;
        ordered.push_back(name);
    }

    m_entries.clear();
    for (const std::string &name : ordered)
        m_entries.push_back({name, states[name]});
}

void Profile::save(const std::string &baseImage, const std::vector<ProfileEntry> &entries)
{
    // A module removed from the image template (for example Terra) can linger in an
    // existing profile.yaml. Drop entries whose module file no longer exists instead of
    // keeping a dangling module reference.
    const fs::path moduleDirectory = fs::path(m_path).parent_path() / "modules";
    const auto moduleExists = [&moduleDirectory](const std::string &name) {
        std::error_code error;
        return fs::is_regular_file(moduleDirectory / (name + ".yaml"), error);
    };

    std::vector<ProfileEntry> live;
    live.reserve(entries.size());
    for (const ProfileEntry &entry : entries) {
        if (moduleExists(entry.name))
            live.push_back(entry);
    }

    std::vector<std::string> lines = m_lines;

    std::map<std::string, std::size_t> existing;
    std::set<std::size_t> removed;
    for (std::size_t index = m_header + 1; index < m_end; ++index) {
        std::smatch match;
        if (!std::regex_match(lines[index], match, profileItemPattern))
            continue;
        const std::string name = match[4].str();
        if (moduleExists(name))
            existing.emplace(name, index);
        else
            removed.insert(index);
    }

    std::map<std::size_t, std::vector<std::string>> insertions;
    for (std::size_t entryIndex = 0; entryIndex < live.size(); ++entryIndex) {
        const std::string &name = live[entryIndex].name;
        const bool enabled = live[entryIndex].enabled;
        const auto found = existing.find(name);
        if (found == existing.end()) {
            std::optional<std::size_t> nextIndex;
            for (std::size_t following = entryIndex + 1; following < live.size(); ++following) {
                const auto next = existing.find(live[following].name);
                if (next != existing.end()) {
                    nextIndex = next->second;
                    break;
                }
            }

            std::size_t lineIndex = 0;
            if (nextIndex) {
                lineIndex = *nextIndex;
            } else if (!existing.empty()) {
                std::size_t maximum = 0;
                for (const auto &entry : existing)
                    maximum = std::max(maximum, entry.second);
                lineIndex = maximum + 1;
            } else {
                lineIndex = m_header + 1;
            }

            std::optional<std::size_t> styleIndex;
            for (const auto &entry : existing) {
                if (entry.second == lineIndex) {
                    styleIndex = entry.second;
                    break;
                }
            }
            if (!styleIndex && !existing.empty()) {
                std::size_t maximum = 0;
                for (const auto &entry : existing)
                    maximum = std::max(maximum, entry.second);
                styleIndex = maximum;
            }

            std::string indent;
            std::string dash = "- ";
            if (styleIndex) {
                std::smatch style;
                if (std::regex_match(lines[*styleIndex], style, profileItemPattern)) {
                    indent = style[1].str();
                    dash = style[3].str();
                }
            }

            const std::string comment = enabled ? "" : "#";
            insertions[lineIndex].push_back(indent + comment + dash + name);
            continue;
        }

        const std::size_t lineIndex = found->second;
        std::smatch match;
        if (!std::regex_match(lines[lineIndex], match, profileItemPattern))
            continue;
        const bool currentlyEnabled = !match[2].matched;
        if (currentlyEnabled != enabled) {
            const std::string marker = enabled ? "" : "#";
            lines[lineIndex] = match[1].str() + marker + match[3].str() + match[4].str()
                + match[5].str();
        }
    }

    std::vector<std::string> output;
    for (std::size_t index = 0; index < lines.size(); ++index) {
        const auto insertion = insertions.find(index);
        if (insertion != insertions.end())
            output.insert(output.end(), insertion->second.begin(), insertion->second.end());
        if (removed.count(index) != 0)
            continue;
        output.push_back(lines[index]);
    }
    const auto tail = insertions.find(lines.size());
    if (tail != insertions.end())
        output.insert(output.end(), tail->second.begin(), tail->second.end());

    for (std::string &line : output) {
        std::smatch match;
        if (std::regex_match(line, match, baseImageReplacePattern)) {
            line = match[1].str() + baseImage + match[2].str();
            break;
        }
    }

    writeFile(m_path, joinLines(output));
}

std::vector<std::string> questions(const Selection &selection)
{
    const std::set<std::string> chosen = selection.chosen();
    std::vector<std::string> asked;
    if (!intersects(chosen, rpmfusionApps()))
        asked.push_back("rpmfusion");

    if (removalsAsked(selection))
        asked.push_back("removals");

    if (!intersects(chosen, browserRepoApps("brave")) && selection.braveRepoEnabled)
        asked.push_back("brave");
    if (!intersects(chosen, browserRepoApps("vivaldi")) && selection.vivaldiRepoEnabled)
        asked.push_back("vivaldi");
    return asked;
}

std::vector<ProfileEntry> resolve(const Profile &profile, const Selection &selection)
{
    const std::vector<std::string> asked = questions(selection);
    const auto wasAsked = [&asked](const std::string &name) {
        return std::find(asked.begin(), asked.end(), name) != asked.end();
    };

    std::vector<ProfileEntry> result;
    for (const ProfileEntry &entry : profile.entries()) {
        const std::string &name = entry.name;
        bool enabled = false;
        if (name == "base") {
            enabled = true;
        } else if (name == "rpmfusion") {
            enabled = !(selection.disableRpmfusion && wasAsked("rpmfusion"));
        } else if (selection.appModules.count(name) != 0) {
            std::set<std::string> selected;
            const auto found = selection.apps.find(name);
            if (found != selection.apps.end())
                selected = found->second;
            std::set<std::string> removals;
            const auto removal = selection.removalApps.find(name);
            if (removal != selection.removalApps.end())
                removals = removal->second;

            std::set<std::string> installs;
            std::set<std::string> selectedRemovals;
            for (const std::string &app : selected) {
                if (removals.count(app) != 0)
                    selectedRemovals.insert(app);
                else
                    installs.insert(app);
            }
            enabled = !installs.empty()
                || (!selectedRemovals.empty()
                    && !(selection.disableRemovals && wasAsked("removals")));
        } else {
            enabled = entry.enabled;
        }
        result.push_back({name, enabled});
    }
    return result;
}

bool repoCommandEnabled(const Module *module, const std::string &repo)
{
    if (module == nullptr)
        return false;
    const std::string &marker = browserRepoUrl(repo);
    for (const std::string &line : module->lines) {
        if (line.find(marker) == std::string::npos
            || line.find("dnf config-manager") == std::string::npos)
            continue;
        const auto first = line.find_first_not_of(" \t");
        const std::string stripped = first == std::string::npos ? "" : line.substr(first);
        return stripped.rfind("#", 0) != 0;
    }
    return false;
}

void setRepoCommand(Module &module, const std::string &repo, bool enabled)
{
    const std::string &marker = browserRepoUrl(repo);
    for (std::size_t index = 0; index < module.lines.size(); ++index) {
        std::string &line = module.lines[index];
        if (line.find(marker) == std::string::npos
            || line.find("dnf config-manager") == std::string::npos)
            continue;

        const auto first = line.find_first_not_of(" \t");
        const std::string indent = first == std::string::npos ? line : line.substr(0, first);
        std::string command = first == std::string::npos ? "" : line.substr(first);
        if (!command.empty() && command.front() == '#') {
            command.erase(0, 1);
            if (!command.empty() && command.front() == ' ')
                command.erase(0, 1);
        }
        if (enabled)
            module.lines[index] = indent + command;
        else
            module.lines[index] = indent + "# " + command;
        return;
    }
}

void apply(const std::string &root, const Selection &selection,
           std::map<std::string, Module> &modules, Profile &profile)
{
    (void)root;
    const std::vector<ProfileEntry> entries = resolve(profile, selection);
    const std::set<std::string> chosenApps = selection.chosen();
    const bool disableRemovals = selection.disableRemovals && removalsAsked(selection);

    for (const ProfileEntry &entry : entries) {
        if (entry.name == "base")
            continue;
        const auto found = modules.find(entry.name);
        if (found == modules.end())
            continue;
        Module &module = found->second;
        if (module.apps.empty())
            continue;

        std::set<std::string> chosen;
        if (entry.enabled) {
            const auto selected = selection.apps.find(entry.name);
            if (selected != selection.apps.end())
                chosen = selected->second;
        }
        if (disableRemovals) {
            const auto removals = selection.removalApps.find(entry.name);
            if (removals != selection.removalApps.end()) {
                for (const std::string &name : removals->second)
                    chosen.erase(name);
            }
        }

        std::vector<std::string> lines = module.lines;
        for (const App &app : module.apps) {
            const bool wanted = chosen.count(app.name) != 0;
            setItem(lines, app.section, app.name, wanted);
            if (app.repo)
                setItem(lines, app.repo->first, app.repo->second, wanted);
        }
        module.lines = lines;
    }

    const auto browsers = modules.find("browsers");
    if (browsers != modules.end()) {
        Module &module = browsers->second;
        const bool braveEnabled = intersects(chosenApps, browserRepoApps("brave"))
            || (selection.braveRepoEnabled && !selection.disableBraveRepo);
        const bool vivaldiEnabled = intersects(chosenApps, browserRepoApps("vivaldi"))
            || (selection.vivaldiRepoEnabled && !selection.disableVivaldiRepo);
        setRepoCommand(module, "brave", braveEnabled);
        setRepoCommand(module, "vivaldi", vivaldiEnabled);
    }

    for (auto &entry : modules) {
        Module &module = entry.second;
        if (module.lines != splitLines(readFile(module.path)))
            writeFile(module.path, joinLines(module.lines));
    }

    profile.save(selection.baseImage, entries);
}

std::pair<bool, std::string> generate(const std::string &root)
{
    const ProcessResult result = runProcess({"dcli-bootc", "gen", "-p", root});
    if (!result.started)
        return {false, "dcli-bootc was not found on PATH."};
    return {result.status == 0, trim(result.output)};
}

} // namespace kineticos
