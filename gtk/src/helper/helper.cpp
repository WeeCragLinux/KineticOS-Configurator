// KineticOS Configurator privileged helper.
//
// This is the only code that runs as root. It is started by pkexec through the
// com.weecraglinux.kinetic-configurator.run-helper polkit action, so the user authenticates
// with the system polkit agent (Noctalia). It supports a fixed, allow-listed set of
// operations and never uses a shell: it execs /usr/bin/dcli-bootc with a fixed argument
// vector after validating the project path.

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace {

const char *const kDcli = "/usr/bin/dcli-bootc";

[[noreturn]] void fail(const std::string &message)
{
    std::fprintf(stderr, "kinetic-configurator-helper: %s\n", message.c_str());
    std::exit(1);
}

bool isProject(const std::string &path)
{
    if (path.empty() || path.front() != '/')
        return false;
    struct stat info;
    const std::string profile = path + "/profile.yaml";
    const std::string modules = path + "/modules";
    if (::stat(profile.c_str(), &info) != 0)
        return false;
    if (!S_ISREG(info.st_mode))
        return false;
    if (::stat(modules.c_str(), &info) != 0)
        return false;
    return S_ISDIR(info.st_mode);
}

} // namespace

int main(int argc, char **argv)
{
    if (argc < 2)
        fail("usage: kinetic-configurator-helper <build|switch> --project <path>");

    const std::string command = argv[1];
    if (command != "build" && command != "switch")
        fail("unsupported operation: " + command);

    std::string project;
    for (int index = 2; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--project" && index + 1 < argc) {
            project = argv[++index];
        } else {
            fail("unexpected argument: " + argument);
        }
    }
    if (project.empty())
        fail("--project is required");
    if (!isProject(project))
        fail("not an image project: " + project);

    std::vector<std::string> arguments{kDcli, command, "-p", project};
    if (command == "build") {
        arguments.push_back("--no-switch");
    } else {
        arguments.push_back("--force");
        arguments.push_back("--reboot");
    }

    std::string display;
    for (const std::string &argument : arguments)
        display += argument + " ";
    std::fprintf(stderr, "kinetic-configurator-helper: running: %s\n", display.c_str());

    std::vector<char *> execArguments;
    execArguments.reserve(arguments.size() + 1);
    for (std::string &argument : arguments)
        execArguments.push_back(argument.data());
    execArguments.push_back(nullptr);

    const pid_t pid = ::fork();
    if (pid < 0)
        fail("fork failed");
    if (pid == 0) {
        ::execv(kDcli, execArguments.data());
        std::fprintf(stderr, "kinetic-configurator-helper: could not run %s: %s\n", kDcli,
                     std::strerror(errno));
        ::_exit(127);
    }

    int status = 0;
    if (::waitpid(pid, &status, 0) < 0)
        fail("waitpid failed");
    const int code = WIFEXITED(status) ? WEXITSTATUS(status)
                                       : (WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 1);
    std::fprintf(stderr, "kinetic-configurator-helper: %s exited with status %d\n",
                 command.c_str(), code);
    return code;
}
