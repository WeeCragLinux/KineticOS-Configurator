#pragma once

#include <string>
#include <vector>

namespace kineticos {

// Result of running an external program without a shell.
struct ProcessResult {
    bool started{false};
    int status{-1};
    std::string output;
};

// Runs argv[0] with the given arguments (no shell), merging stdout and stderr. When timeoutMs
// is non-zero the child is killed after that long. Returns started=false when the program
// could not be launched.
ProcessResult runProcess(const std::vector<std::string> &argv, int timeoutMs = 0);

// Whether a program can be resolved on PATH.
bool programOnPath(const std::string &program);

} // namespace kineticos
