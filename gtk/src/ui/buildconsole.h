#pragma once

#include <gtkmm/box.h>
#include <gtkmm/button.h>
#include <gtkmm/textview.h>
#include <gtkmm/window.h>
#include <sigc++/sigc++.h>

#include <string>
#include <vector>

namespace kineticos {

// Runs a long command and shows its live output. A secondary window with its own header bar,
// streaming the merged stdout/stderr, and answering the build's Flatpak yes/no prompt.
class BuildConsole final : public Gtk::Window {
public:
    BuildConsole(Gtk::Window &parent, const std::string &title, std::vector<std::string> command);
    ~BuildConsole() override;

    // Emitted once when the window closes: true when the command exited 0.
    sigc::signal<void(bool)> &signalFinished() { return m_finished; }

    // Starts the command. Call after connecting signalFinished().
    void run();

    std::string output() const;

    // Called from the GLib async read callback (public so the C trampoline can reach it).
    void readReady(long count);

private:
    void append(const std::string &text);
    void updatePrompt();
    void answer(bool yes);
    void onAction();
    void finish(bool success);

    std::vector<std::string> m_command;
    void *m_process{nullptr}; // GSubprocess*
    void *m_stdout{nullptr};  // GInputStream*
    void *m_stdin{nullptr};   // GOutputStream*
    char m_readBuffer[4096];
    bool m_running{false};
    bool m_emitted{false};
    unsigned int m_promptCount{0};
    unsigned int m_answeredPrompts{0};

    Glib::RefPtr<Gtk::TextBuffer> m_text;
    Gtk::TextView m_view;
    Gtk::Box m_promptRow;
    Gtk::Button m_yes;
    Gtk::Button m_no;
    Gtk::Button m_action;
    sigc::signal<void(bool)> m_finished;
};

} // namespace kineticos
