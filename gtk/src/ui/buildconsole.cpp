#include "ui/buildconsole.h"

#include <gio/gio.h>
#include <glibmm/main.h>
#include <glibmm/markup.h>
#include <gtkmm/headerbar.h>
#include <gtkmm/label.h>
#include <gtkmm/scrolledwindow.h>

#include <algorithm>
#include <cctype>

namespace kineticos {

namespace {

// Yes/no markers printed by the confirmation prompts a build can show. The haystack is
// lowercased before searching, so "[y/n]" matches "[y/N]", "[Y/n]" and friends too.
const char *const yesNoMarkers[] = {
    "[y/n]",
    "(y/n)",
    "[yes/no]",
    "(yes/no)",
};

// The privileged build runs as root, so answering Yes would install the Flatpaks into
// root's home. The window performs the real user-scoped sync after the build, so this
// question is always answered No.
const char *const flatpakPrompt = "apply these changes to your user flatpak installation?";

std::string lowercase(std::string text)
{
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}

void onReadReady(GObject *source, GAsyncResult *result, gpointer data)
{
    auto *self = static_cast<BuildConsole *>(data);
    GError *error = nullptr;
    const gssize count = g_input_stream_read_finish(G_INPUT_STREAM(source), result, &error);
    if (error)
        g_error_free(error);
    self->readReady(static_cast<long>(count));
}

} // namespace

BuildConsole::BuildConsole(Gtk::Window &parent, const std::string &title,
                           std::vector<std::string> command)
    : m_command(std::move(command))
    , m_text(Gtk::TextBuffer::create())
    , m_promptRow(Gtk::Orientation::HORIZONTAL, 8)
    , m_yes("Yes")
    , m_no("No")
    , m_action("Cancel")
{
    set_title(title);
    set_transient_for(parent);
    set_modal(true);
    set_default_size(760, 480);
    set_hide_on_close(false);

    auto *header = Gtk::make_managed<Gtk::HeaderBar>();
    auto *headerTitle = Gtk::make_managed<Gtk::Label>();
    headerTitle->set_markup("<span weight=\"bold\">" + Glib::Markup::escape_text(title) + "</span>");
    headerTitle->add_css_class("wordmark");
    header->set_title_widget(*headerTitle);
    set_titlebar(*header);

    auto *root = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::VERTICAL, 10);
    root->add_css_class("dialog-body");

    auto *outputLabel = Gtk::make_managed<Gtk::Label>("Command output:");
    outputLabel->add_css_class("muted");
    outputLabel->set_halign(Gtk::Align::START);
    root->append(*outputLabel);

    m_view.set_buffer(m_text);
    m_view.set_editable(false);
    m_view.set_cursor_visible(false);
    m_view.set_monospace(true);
    m_view.set_wrap_mode(Gtk::WrapMode::WORD_CHAR);
    m_view.add_css_class("console-view");
    m_view.set_vexpand(true);
    auto *scroller = Gtk::make_managed<Gtk::ScrolledWindow>();
    scroller->set_policy(Gtk::PolicyType::NEVER, Gtk::PolicyType::AUTOMATIC);
    scroller->set_vexpand(true);
    scroller->set_child(m_view);
    root->append(*scroller);

    m_promptRow.set_visible(false);
    auto *promptLabel = Gtk::make_managed<Gtk::Label>(
        "The command is waiting for a yes or no answer:");
    promptLabel->set_hexpand(true);
    promptLabel->set_halign(Gtk::Align::START);
    m_promptRow.append(*promptLabel);
    m_promptRow.append(m_yes);
    m_promptRow.append(m_no);
    root->append(m_promptRow);

    m_action.set_halign(Gtk::Align::END);
    root->append(m_action);

    set_child(*root);

    m_yes.signal_clicked().connect([this] { answer(true); });
    m_no.signal_clicked().connect([this] { answer(false); });
    m_action.signal_clicked().connect([this] { onAction(); });
}

BuildConsole::~BuildConsole()
{
    if (m_running && m_process != nullptr)
        g_subprocess_force_exit(static_cast<GSubprocess *>(m_process));
    if (m_stdin != nullptr)
        g_object_unref(m_stdin);
    if (m_stdout != nullptr)
        g_object_unref(m_stdout);
    if (m_process != nullptr)
        g_object_unref(m_process);
}

void BuildConsole::run()
{
    std::vector<const gchar *> argv;
    argv.reserve(m_command.size() + 1);
    for (const std::string &argument : m_command)
        argv.push_back(argument.c_str());
    argv.push_back(nullptr);

    GError *error = nullptr;
    m_process = g_subprocess_newv(
        argv.data(),
        static_cast<GSubprocessFlags>(G_SUBPROCESS_FLAGS_STDOUT_PIPE
                                      | G_SUBPROCESS_FLAGS_STDERR_MERGE
                                      | G_SUBPROCESS_FLAGS_STDIN_PIPE),
        &error);
    if (m_process == nullptr) {
        append(std::string("Could not start command. ") + (error ? error->message : "")
               + "\n");
        if (error)
            g_error_free(error);
        m_action.set_label("Close");
        finish(false);
        return;
    }

    m_running = true;
    m_stdout = g_subprocess_get_stdout_pipe(static_cast<GSubprocess *>(m_process));
    m_stdin = g_subprocess_get_stdin_pipe(static_cast<GSubprocess *>(m_process));
    g_input_stream_read_async(static_cast<GInputStream *>(m_stdout), m_readBuffer,
                              sizeof m_readBuffer, G_PRIORITY_DEFAULT, nullptr, onReadReady,
                              this);
}

void BuildConsole::append(const std::string &text)
{
    m_text->insert(m_text->end(), text);
    // Keep the newest output visible.
    auto end = m_text->create_mark(m_text->end());
    m_view.scroll_to(end);
    m_text->delete_mark(end);
}

void BuildConsole::readReady(long count)
{
    if (count > 0) {
        append(std::string(m_readBuffer, static_cast<std::size_t>(count)));
        updatePrompt();
        if (m_stdout != nullptr)
            g_input_stream_read_async(static_cast<GInputStream *>(m_stdout), m_readBuffer,
                                      sizeof m_readBuffer, G_PRIORITY_DEFAULT, nullptr,
                                      onReadReady, this);
        return;
    }

    // End of output: reap the process and report its status.
    m_running = false;
    if (m_process != nullptr) {
        GError *error = nullptr;
        g_subprocess_wait(static_cast<GSubprocess *>(m_process), nullptr, &error);
        if (error)
            g_error_free(error);
    }
    const bool ok = m_process != nullptr
        && g_subprocess_get_successful(static_cast<GSubprocess *>(m_process));
    m_promptRow.set_visible(false);
    m_action.set_label("Close");
    finish(ok);
}

void BuildConsole::updatePrompt()
{
    const std::string haystack = lowercase(m_text->get_text());

    // Auto-answer the root build's Flatpak question once. The user-scoped sync runs
    // separately after the build, so the Yes/No row is never shown for it.
    const bool askedAboutFlatpaks = haystack.find(flatpakPrompt) != std::string::npos;
    if (askedAboutFlatpaks && !m_flatpakAnswered) {
        m_flatpakAnswered = true;
        sendAnswer(false);
    }

    unsigned int occurrences = 0;
    for (const char *marker : yesNoMarkers) {
        for (std::size_t at = haystack.find(marker); at != std::string::npos;
             at = haystack.find(marker, at + 1))
            ++occurrences;
    }
    m_promptCount = occurrences;
    m_promptRow.set_visible(m_running && m_promptCount > m_answeredPrompts);
}

void BuildConsole::sendAnswer(const bool yes)
{
    if (!m_running || m_stdin == nullptr)
        return;
    const std::string line = yes ? "y\n" : "n\n";
    gsize written = 0;
    g_output_stream_write_all(static_cast<GOutputStream *>(m_stdin), line.data(), line.size(),
                              &written, nullptr, nullptr);
}

void BuildConsole::answer(const bool yes)
{
    sendAnswer(yes);
    m_answeredPrompts = m_promptCount;
    m_promptRow.set_visible(false);
}

void BuildConsole::onAction()
{
    if (m_running) {
        if (m_process != nullptr)
            g_subprocess_force_exit(static_cast<GSubprocess *>(m_process));
        return;
    }
    close();
}

void BuildConsole::finish(const bool success)
{
    if (m_emitted)
        return;
    m_emitted = true;
    m_finished.emit(success);
}

std::string BuildConsole::output() const
{
    return m_text->get_text();
}

} // namespace kineticos
