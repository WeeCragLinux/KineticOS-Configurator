#include "core/template_sync.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

// Port of source/configurator/core/template_sync.py. The regexes and the merge order are
// copied from the Python implementation, which is the specification.
namespace kineticos::template_sync {

namespace {

namespace fs = std::filesystem;

using Path = std::vector<std::string>;
using Key = std::pair<Path, std::string>;

const std::regex profileItemPattern(R"(^(\s*)(#\s*)?-\s*(\S+)\s*$)");
const std::regex itemPattern(R"(^(\s*)(#\s*)?-\s+(\S+)(.*)$)");
const std::regex headerPattern(R"(^(\s*)([A-Za-z_][\w-]*):(?:[ \t]*(.*))?$)");
const std::regex emptyListPattern(R"(\[\s*\])");

struct ListEntry {
    std::size_t index{0};
    Path path;
    std::string name;
    std::string line;
};

struct MappingHeader {
    std::size_t index{0};
    Path path;
    std::size_t indent{0};
    std::string line;
    std::string value;
};

struct ParsedModule {
    std::map<Key, ListEntry> entries;
    std::vector<MappingHeader> headers;
};

struct ProfileBlock {
    std::optional<std::size_t> header;
    std::optional<std::size_t> end;
    std::map<std::string, std::pair<std::size_t, std::string>> entries;
};

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

std::string trim(const std::string &text)
{
    const char *whitespace = " \t\r\n\f\v";
    const auto first = text.find_first_not_of(whitespace);
    if (first == std::string::npos)
        return {};
    return text.substr(first, text.find_last_not_of(whitespace) - first + 1);
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

std::size_t expandedIndentLength(const std::string &indent)
{
    std::size_t column = 0;
    for (const char character : indent) {
        if (character == '\t')
            column += 8 - (column % 8);
        else
            ++column;
    }
    return column;
}

ProfileBlock profileBlock(const std::vector<std::string> &lines)
{
    ProfileBlock block;
    for (std::size_t index = 0; index < lines.size(); ++index) {
        if (lines[index].rfind("enabled_modules:", 0) == 0) {
            block.header = index;
            break;
        }
    }
    if (!block.header)
        return block;

    std::size_t end = *block.header + 1;
    while (end < lines.size()) {
        std::smatch match;
        if (!std::regex_match(lines[end], match, profileItemPattern))
            break;
        block.entries.emplace(match[3].str(), std::make_pair(end, lines[end]));
        ++end;
    }
    block.end = end;
    return block;
}

std::optional<std::string> profileRow(const std::string &text, const std::string &name)
{
    const ProfileBlock block = profileBlock(splitLines(text));
    const auto found = block.entries.find(name);
    if (found == block.entries.end())
        return std::nullopt;
    return found->second.second;
}

ParsedModule parseModuleLines(const std::vector<std::string> &lines)
{
    ParsedModule parsed;
    std::vector<std::pair<std::size_t, std::string>> stack;
    for (std::size_t index = 0; index < lines.size(); ++index) {
        std::smatch item;
        if (std::regex_match(lines[index], item, itemPattern)) {
            Path path;
            for (const auto &frame : stack)
                path.push_back(frame.second);
            // Script bodies are arbitrary shell, not template list entries.
            if (!path.empty() && path.front() != "scripts") {
                ListEntry entry;
                entry.index = index;
                entry.path = path;
                entry.name = item[3].str();
                entry.line = lines[index];
                parsed.entries.emplace(Key(path, entry.name), entry);
            }
            continue;
        }

        std::smatch header;
        if (!std::regex_match(lines[index], header, headerPattern))
            continue;
        const std::size_t indent = expandedIndentLength(header[1].str());
        while (!stack.empty() && stack.back().first >= indent)
            stack.pop_back();
        stack.push_back({indent, header[2].str()});

        Path path;
        for (const auto &frame : stack)
            path.push_back(frame.second);
        MappingHeader mapping;
        mapping.index = index;
        mapping.path = path;
        mapping.indent = indent;
        mapping.line = lines[index];
        mapping.value = header[3].matched ? header[3].str() : "";
        parsed.headers.push_back(mapping);
    }
    return parsed;
}

std::set<Path> headerPaths(const std::vector<MappingHeader> &headers)
{
    std::set<Path> paths;
    for (const MappingHeader &header : headers)
        paths.insert(header.path);
    return paths;
}

std::size_t sectionEnd(const std::vector<std::string> &lines, const MappingHeader &header)
{
    const ParsedModule parsed = parseModuleLines(lines);
    for (const MappingHeader &candidate : parsed.headers) {
        if (candidate.index > header.index && candidate.indent <= header.indent)
            return candidate.index;
    }
    return lines.size();
}

std::vector<std::string> headerBlock(const std::vector<std::string> &lines,
                                     const std::vector<MappingHeader> &headers,
                                     const MappingHeader &header)
{
    std::size_t end = lines.size();
    for (const MappingHeader &candidate : headers) {
        if (candidate.index > header.index && candidate.indent <= header.indent) {
            end = candidate.index;
            break;
        }
    }
    return std::vector<std::string>(lines.begin() + static_cast<std::ptrdiff_t>(header.index),
                                    lines.begin() + static_cast<std::ptrdiff_t>(end));
}

bool isPrefixOf(const Path &prefix, const Path &path)
{
    if (path.size() < prefix.size())
        return false;
    return std::equal(prefix.begin(), prefix.end(), path.begin());
}

// Copy newly introduced list sections, but not locally removed sections.
void appendNewHeaders(std::vector<std::string> &localLines,
                      const std::vector<MappingHeader> &baseHeaders,
                      const std::vector<std::string> &upstreamLines,
                      const std::vector<MappingHeader> &upstreamHeaders)
{
    const std::set<Path> basePaths = headerPaths(baseHeaders);
    const ParsedModule upstream = parseModuleLines(upstreamLines);
    ParsedModule local = parseModuleLines(localLines);
    std::set<Path> localPaths = headerPaths(local.headers);

    for (const MappingHeader &header : upstreamHeaders) {
        if (!header.path.empty() && header.path.front() == "scripts")
            continue;
        if (basePaths.count(header.path) != 0 || localPaths.count(header.path) != 0)
            continue;

        bool hasEntry = false;
        for (const auto &entry : upstream.entries) {
            if (isPrefixOf(header.path, entry.second.path)) {
                hasEntry = true;
                break;
            }
        }
        if (!hasEntry)
            continue;

        // If a previously existing parent was deleted locally, keep it deleted.
        bool deletedParent = false;
        for (std::size_t depth = 1; depth < header.path.size(); ++depth) {
            const Path prefix(header.path.begin(),
                              header.path.begin() + static_cast<std::ptrdiff_t>(depth));
            if (basePaths.count(prefix) != 0 && localPaths.count(prefix) == 0) {
                deletedParent = true;
                break;
            }
        }
        if (deletedParent)
            continue;

        const std::vector<std::string> block = headerBlock(upstreamLines, upstreamHeaders, header);
        if (header.path.size() == 1) {
            if (!localLines.empty() && !trim(localLines.back()).empty())
                localLines.push_back("");
            localLines.insert(localLines.end(), block.begin(), block.end());
        } else {
            const Path parentPath(header.path.begin(), header.path.end() - 1);
            const MappingHeader *parent = nullptr;
            for (const MappingHeader &candidate : local.headers) {
                if (candidate.path == parentPath) {
                    parent = &candidate;
                    break;
                }
            }
            if (parent == nullptr)
                continue;
            const std::size_t insertAt = sectionEnd(localLines, *parent);
            localLines.insert(localLines.begin() + static_cast<std::ptrdiff_t>(insertAt),
                              block.begin(), block.end());
        }

        // Reparse after each copied block so nested headers are not duplicated.
        local = parseModuleLines(localLines);
        localPaths = headerPaths(local.headers);
    }
}

bool insertEntry(std::vector<std::string> &localLines, const ListEntry &entry,
                 const std::map<Key, ListEntry> &upstreamEntries)
{
    const ParsedModule local = parseModuleLines(localLines);
    if (local.entries.count(Key(entry.path, entry.name)) != 0)
        return false;

    std::vector<const ListEntry *> siblings;
    for (const auto &candidate : upstreamEntries) {
        if (candidate.second.path == entry.path)
            siblings.push_back(&candidate.second);
    }
    std::sort(siblings.begin(), siblings.end(),
              [](const ListEntry *left, const ListEntry *right) {
                  return left->index < right->index;
              });

    std::size_t position = 0;
    for (std::size_t index = 0; index < siblings.size(); ++index) {
        if (siblings[index]->name == entry.name) {
            position = index;
            break;
        }
    }

    for (std::size_t index = position; index-- > 0;) {
        const ListEntry *previous = siblings[index];
        const auto existing = local.entries.find(Key(previous->path, previous->name));
        if (existing != local.entries.end()) {
            localLines.insert(localLines.begin()
                                  + static_cast<std::ptrdiff_t>(existing->second.index + 1),
                              entry.line);
            return true;
        }
    }
    for (std::size_t index = position + 1; index < siblings.size(); ++index) {
        const ListEntry *following = siblings[index];
        const auto existing = local.entries.find(Key(following->path, following->name));
        if (existing != local.entries.end()) {
            localLines.insert(localLines.begin()
                                  + static_cast<std::ptrdiff_t>(existing->second.index),
                              entry.line);
            return true;
        }
    }

    const MappingHeader *header = nullptr;
    for (const MappingHeader &candidate : local.headers) {
        if (candidate.path == entry.path) {
            header = &candidate;
            break;
        }
    }
    if (header == nullptr) {
        // A missing section present in the base was intentionally removed locally.
        return false;
    }
    if (std::regex_search(header->value, emptyListPattern)) {
        localLines[header->index] = std::regex_replace(header->line, emptyListPattern, "",
                                                       std::regex_constants::format_first_only);
        localLines.insert(localLines.begin() + static_cast<std::ptrdiff_t>(header->index + 1),
                          entry.line);
        return true;
    }

    const std::size_t insertAt = sectionEnd(localLines, *header);
    localLines.insert(localLines.begin() + static_cast<std::ptrdiff_t>(insertAt), entry.line);
    return true;
}

} // namespace

void SyncSummary::include(const SyncSummary &other)
{
    added += other.added;
    removed += other.removed;
    retained += other.retained;
}

std::pair<std::string, SyncSummary> mergeProfileEntries(const std::string &baseText,
                                                        const std::string &localText,
                                                        const std::string &upstreamText)
{
    std::vector<std::string> localLines = splitLines(localText);
    const ProfileBlock baseBlock = profileBlock(splitLines(baseText));
    const ProfileBlock upstreamBlock = profileBlock(splitLines(upstreamText));
    ProfileBlock localBlock = profileBlock(localLines);
    if (!baseBlock.header || !upstreamBlock.header || !localBlock.header)
        throw std::runtime_error("profile.yaml must contain an enabled_modules list.");
    SyncSummary summary;

    // Remove an upstream-deleted module only when its local row is untouched.
    std::vector<std::size_t> removeIndices;
    for (const auto &baseEntry : baseBlock.entries) {
        if (upstreamBlock.entries.count(baseEntry.first) != 0)
            continue;
        const auto current = localBlock.entries.find(baseEntry.first);
        if (current == localBlock.entries.end())
            continue;
        if (current->second.second == baseEntry.second.second) {
            removeIndices.push_back(current->second.first);
            summary.removed += 1;
        } else {
            summary.retained += 1;
        }
    }
    std::sort(removeIndices.begin(), removeIndices.end());
    for (auto index = removeIndices.rbegin(); index != removeIndices.rend(); ++index) {
        localLines.erase(localLines.begin() + static_cast<std::ptrdiff_t>(*index));
    }

    // New module rows inherit upstream's initial enabled/disabled state.
    localBlock = profileBlock(localLines);
    std::vector<std::pair<std::string, std::pair<std::size_t, std::string>>> upstreamRows;
    for (const auto &entry : upstreamBlock.entries)
        upstreamRows.emplace_back(entry.first, entry.second);
    std::sort(upstreamRows.begin(), upstreamRows.end(),
              [](const auto &left, const auto &right) {
                  return left.second.first < right.second.first;
              });

    for (std::size_t position = 0; position < upstreamRows.size(); ++position) {
        const std::string &name = upstreamRows[position].first;
        const std::string &line = upstreamRows[position].second.second;
        if (baseBlock.entries.count(name) != 0 || localBlock.entries.count(name) != 0)
            continue;

        // Place new modules near their upstream neighbors, without reordering
        // any rows that already belong to the user.
        localBlock = profileBlock(localLines);
        std::size_t insertAt = localBlock.end ? *localBlock.end : localLines.size();
        bool foundPrior = false;
        for (std::size_t index = position; index-- > 0;) {
            const auto prior = localBlock.entries.find(upstreamRows[index].first);
            if (prior != localBlock.entries.end()) {
                insertAt = prior->second.first + 1;
                foundPrior = true;
                break;
            }
        }
        if (!foundPrior) {
            for (std::size_t index = position + 1; index < upstreamRows.size(); ++index) {
                const auto following = localBlock.entries.find(upstreamRows[index].first);
                if (following != localBlock.entries.end()) {
                    insertAt = following->second.first;
                    break;
                }
            }
        }
        localLines.insert(localLines.begin() + static_cast<std::ptrdiff_t>(insertAt), line);
        summary.added += 1;
    }

    return {joinLines(localLines), summary};
}

std::pair<std::string, SyncSummary> mergeModuleEntries(const std::string &baseText,
                                                       const std::string &localText,
                                                       const std::string &upstreamText)
{
    std::vector<std::string> localLines = splitLines(localText);
    const std::vector<std::string> baseLines = splitLines(baseText);
    const std::vector<std::string> upstreamLines = splitLines(upstreamText);
    const ParsedModule base = parseModuleLines(baseLines);
    const ParsedModule local = parseModuleLines(localLines);
    const ParsedModule upstream = parseModuleLines(upstreamLines);
    SyncSummary summary;

    // Retain a removed item if the user changed its line (including its toggle).
    std::vector<std::size_t> removeIndices;
    for (const auto &baseEntry : base.entries) {
        if (upstream.entries.count(baseEntry.first) != 0)
            continue;
        const auto current = local.entries.find(baseEntry.first);
        if (current == local.entries.end())
            continue;
        if (current->second.line == baseEntry.second.line) {
            removeIndices.push_back(current->second.index);
            summary.removed += 1;
        } else {
            summary.retained += 1;
        }
    }
    std::sort(removeIndices.begin(), removeIndices.end());
    for (auto index = removeIndices.rbegin(); index != removeIndices.rend(); ++index) {
        localLines.erase(localLines.begin() + static_cast<std::ptrdiff_t>(*index));
    }

    // Add newly introduced sections first, then entries in existing sections.
    appendNewHeaders(localLines, base.headers, upstreamLines, upstream.headers);

    std::vector<const ListEntry *> ordered;
    for (const auto &entry : upstream.entries)
        ordered.push_back(&entry.second);
    std::sort(ordered.begin(), ordered.end(),
              [](const ListEntry *left, const ListEntry *right) {
                  return left->index < right->index;
              });

    for (const ListEntry *entry : ordered) {
        const Key key(entry->path, entry->name);
        if (base.entries.count(key) != 0)
            continue;
        const ParsedModule current = parseModuleLines(localLines);
        if (current.entries.count(key) != 0)
            continue;
        // Do not recreate a list section that was present in the base and
        // deliberately removed from the user's local file.
        const std::set<Path> currentPaths = headerPaths(current.headers);
        const std::set<Path> basePaths = headerPaths(base.headers);
        if (currentPaths.count(entry->path) == 0 && basePaths.count(entry->path) != 0)
            continue;
        insertEntry(localLines, *entry, upstream.entries);
    }

    const ParsedModule finalParsed = parseModuleLines(localLines);
    for (const auto &upstreamEntry : upstream.entries) {
        if (base.entries.count(upstreamEntry.first) != 0)
            continue;
        if (finalParsed.entries.count(upstreamEntry.first) != 0
            && local.entries.count(upstreamEntry.first) == 0) {
            summary.added += 1;
        }
    }
    return {joinLines(localLines), summary};
}

SyncSummary mergeProjectEntries(const std::string &root,
                                const std::map<std::string, std::string> &baseFiles,
                                const std::map<std::string, std::string> &upstreamFiles)
{
    SyncSummary summary;
    const fs::path profilePath = fs::path(root) / "profile.yaml";
    const std::string localProfile = readFile(profilePath.string());
    const std::string &baseProfile = baseFiles.at("profile.yaml");
    const std::string &upstreamProfile = upstreamFiles.at("profile.yaml");

    struct Check {
        const char *label;
        const std::string *content;
    };
    const Check checks[] = {
        {"base", &baseProfile},
        {"local", &localProfile},
        {"upstream", &upstreamProfile},
    };
    for (const Check &check : checks) {
        if (!profileBlock(splitLines(*check.content)).header)
            throw std::runtime_error(std::string("The ") + check.label
                                     + " profile.yaml has no enabled_modules list.");
    }

    const auto mergedProfile = mergeProfileEntries(baseProfile, localProfile, upstreamProfile);
    if (mergedProfile.first != localProfile)
        writeFile(profilePath.string(), mergedProfile.first);
    summary.include(mergedProfile.second);

    std::set<std::string> moduleNames;
    const auto collect = [&moduleNames](const std::map<std::string, std::string> &files) {
        for (const auto &file : files) {
            const std::string &name = file.first;
            if (name.rfind("modules/", 0) == 0 && name.size() > 7
                && name.compare(name.size() - 5, 5, ".yaml") == 0) {
                moduleNames.insert(name.substr(8));
            }
        }
    };
    collect(baseFiles);
    collect(upstreamFiles);

    for (const std::string &name : moduleNames) {
        const std::string relative = "modules/" + name;
        const fs::path path = fs::path(root) / relative;
        const auto baseFound = baseFiles.find(relative);
        const auto upstreamFound = upstreamFiles.find(relative);
        const std::string *baseText =
            baseFound != baseFiles.end() ? &baseFound->second : nullptr;
        const std::string *upstreamText =
            upstreamFound != upstreamFiles.end() ? &upstreamFound->second : nullptr;
        std::error_code error;
        const bool localExists = fs::is_regular_file(path, error);
        std::optional<std::string> localText;
        if (localExists)
            localText = readFile(path.string());

        if (baseText == nullptr && upstreamText != nullptr) {
            if (!localText) {
                fs::create_directories(path.parent_path());
                writeFile(path.string(), *upstreamText);
                summary.added += 1;
            }
            continue;
        }

        if (upstreamText == nullptr && baseText != nullptr) {
            if (!localText)
                continue;
            const std::string moduleName = fs::path(relative).stem().string();
            const bool profileUnchanged =
                profileRow(localProfile, moduleName) == profileRow(baseProfile, moduleName);
            if (*localText == *baseText && profileUnchanged) {
                fs::remove(path);
                summary.removed += 1;
            } else {
                summary.retained += 1;
            }
            continue;
        }

        if (baseText == nullptr || upstreamText == nullptr || !localText) {
            // A locally deleted module remains deleted; an unknown state is
            // safer to retain than to recreate or overwrite.
            continue;
        }

        const auto mergedModule = mergeModuleEntries(*baseText, *localText, *upstreamText);
        if (mergedModule.first != *localText)
            writeFile(path.string(), mergedModule.first);
        summary.include(mergedModule.second);
    }

    return summary;
}

} // namespace kineticos::template_sync
