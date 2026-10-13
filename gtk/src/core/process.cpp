#include "core/process.h"

#include <gio/gio.h>
#include <glib.h>
#include <giomm/cancellable.h>
#include <giomm/subprocess.h>
#include <giomm/subprocesslauncher.h>
#include <glibmm/error.h>
#include <glibmm/main.h>
#include <glibmm/miscutils.h>

namespace kineticos {

namespace {

struct TimeoutState {
    GCancellable *cancellable{nullptr};
    GSubprocess *subprocess{nullptr};
};

gboolean onTimeout(gpointer data)
{
    auto *state = static_cast<TimeoutState *>(data);
    if (state->cancellable != nullptr)
        g_cancellable_cancel(state->cancellable);
    if (state->subprocess != nullptr)
        g_subprocess_force_exit(state->subprocess);
    return G_SOURCE_REMOVE;
}

} // namespace

ProcessResult runProcess(const std::vector<std::string> &argv, const int timeoutMs)
{
    ProcessResult result;
    if (argv.empty())
        return result;

    Glib::RefPtr<Gio::Subprocess> subprocess;
    try {
        subprocess = Gio::Subprocess::create(
            argv, Gio::Subprocess::Flags::STDOUT_PIPE | Gio::Subprocess::Flags::STDERR_MERGE);
    } catch (const Glib::Error &) {
        // The program could not be launched; started stays false.
        return result;
    }
    if (!subprocess)
        return result;
    result.started = true;

    const Glib::RefPtr<Gio::Cancellable> cancellable = Gio::Cancellable::create();

    // communicate() iterates the thread-default main context, so a timeout source attached
    // there can cancel the read and kill the child once the deadline elapses.
    const Glib::RefPtr<Glib::MainContext> context = Glib::MainContext::create();
    GMainContext *rawContext = context->gobj();
    g_main_context_push_thread_default(rawContext);

    TimeoutState state;
    state.cancellable = cancellable->gobj();
    state.subprocess = subprocess->gobj();

    GSource *timeoutSource = nullptr;
    if (timeoutMs > 0) {
        timeoutSource = g_timeout_source_new(static_cast<guint>(timeoutMs));
        g_source_set_callback(timeoutSource, &onTimeout, &state, nullptr);
        g_source_attach(timeoutSource, rawContext);
    }

    GBytes *stdoutBytes = nullptr;
    GError *error = nullptr;
    g_subprocess_communicate(subprocess->gobj(), nullptr, cancellable->gobj(), &stdoutBytes,
                             nullptr, &error);
    if (error != nullptr)
        g_error_free(error);

    if (timeoutSource != nullptr) {
        g_source_destroy(timeoutSource);
        g_source_unref(timeoutSource);
    }
    g_main_context_pop_thread_default(rawContext);

    if (stdoutBytes != nullptr) {
        gsize length = 0;
        const auto *data = static_cast<const char *>(g_bytes_get_data(stdoutBytes, &length));
        if (length > 0)
            result.output.assign(data, length);
        g_bytes_unref(stdoutBytes);
    }

    try {
        subprocess->wait();
    } catch (const Glib::Error &) {
        // The child was already reaped or was killed by the timeout.
    }

    result.status = subprocess->get_if_exited() ? subprocess->get_exit_status() : -1;
    return result;
}

bool programOnPath(const std::string &program)
{
    return !Glib::find_program_in_path(program).empty();
}

} // namespace kineticos
