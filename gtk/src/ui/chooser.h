#pragma once

#include "core/settings.h"
#include "core/workspace.h"
#include "ui/asynctask.h"

#include <gtkmm/application.h>
#include <gtkmm/box.h>
#include <gtkmm/label.h>
#include <gtkmm/spinner.h>
#include <gtkmm/window.h>
#include <sigc++/sigc++.h>

#include <memory>
#include <string>

namespace kineticos {

// The first window: open, clone, update or reset an image project.
class ChooserWindow final : public Gtk::Window {
public:
    ChooserWindow(const Glib::RefPtr<Gtk::Application> &application, Settings settings);
    ~ChooserWindow() override;

    // Emitted with the chosen project root once the user opens a valid project.
    sigc::signal<void(std::string)> &signalChosen() { return m_chosen; }

private:
    void build();
    void finishWith(const std::string &path);
    void chooseExisting();
    void chooseClone();
    void confirmUpdate();
    void confirmReset();
    void runGit(const std::string &operation, const std::string &path);
    void showBusy(const std::string &message);
    void hideBusy();

    Settings m_settings;
    std::string m_saved;
    Gtk::Box m_body;
    std::unique_ptr<Gtk::Window> m_busy;
    Gtk::Label *m_busyLabel{nullptr};
    Gtk::Spinner *m_busySpinner{nullptr};
    AsyncTask<GitResult> m_task;
    sigc::signal<void(std::string)> m_chosen;
};

} // namespace kineticos
