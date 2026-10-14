#pragma once

#include <string>

namespace kineticos {

// Reading of dcli-bootc console output. dcli-bootc decides, from the built image digest and
// the booted deployment digest, whether a build or switch actually changes anything, and says
// so in its output. The app uses those lines to avoid offering (or claiming) a switch to an
// image identical to the one that is already booted.
//
// The strings below come from dcli-bootc 0.6.0 (src/commands/build.rs and src/bootc.rs). Each
// transcript is lowercased before matching, so the capitalised variants all match, and the
// colour codes dcli-bootc adds on a terminal do not interfere with finding the sentence.

// True when a `dcli-bootc build` transcript reports that the freshly built image is identical
// to the deployment the system is currently booted from.
bool buildReportedIdenticalImage(const std::string &buildOutput);

// True when a `dcli-bootc switch` transcript reports that nothing new was staged, so the next
// boot would change nothing (the switch was a no-op).
bool switchReportedNothingStaged(const std::string &switchOutput);

} // namespace kineticos
