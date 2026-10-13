#pragma once

#include "core/project.h"
#include "core/settings.h"
#include "ui/asynctask.h"

#include <gtkmm/aboutdialog.h>
#include <gtkmm/applicationwindow.h>
#include <gtkmm/box.h>
#include <gtkmm/button.h>
#include <gtkmm/headerbar.h>
#include <gtkmm/label.h>
#include <gtkmm/menubutton.h>
#include <gtkmm/revealer.h>
#include <gtkmm/stack.h>

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace kineticos {

class ThemeWatcher;
class HelpWindow;
class BuildConsole;
class BasePage;
class ModulePage;
class OptionalPage;
class ReviewPage;

enum class NoticeKind { Info, Positive, Neutral, Negative };

// The main window: standard header bar, title bar modes and the configuration wizard.
class Window final : public Gtk::ApplicationWindow {
public:
    Window(const Glib::RefPtr<Gtk::Application> &application, std::string root,
           Settings settings);
    ~Window() override;

    Selection &selection() { return m_selection; }
    const std::map<std::string, Module> &modules() const { return m_modules; }
    const Profile &profile() const { return m_profile; }
    const std::map<std::string, std::string> &baseDescriptions() const
    {
        return m_baseDescriptions;
    }

    void notify(const std::string &text, NoticeKind kind, unsigned int timeoutMs);
    // Recomputes the header buttons after a page changes the selection.
    void refreshFlow();

private:
    void buildHeader();
    void buildBody();
    void buildActions(const Glib::RefPtr<Gtk::Application> &application);
    void applyTitleBar(bool system);

    std::vector<Gtk::Widget *> flow() const;
    int currentIndex();
    void go(int index);
    void onBack();
    void onPrimary();
    void writeAndBuild();
    void showAbout();
    void showHelp();
    void focusPrimary();
    void watchAltTap(Gtk::Widget &widget);

    std::string m_root;
    Settings m_settings;
    Profile m_profile;
    std::map<std::string, Module> m_modules;
    Selection m_selection;
    std::map<std::string, std::string> m_baseDescriptions;

    Gtk::HeaderBar m_header;
    Gtk::Box m_content;
    Gtk::Box m_body;
    Gtk::Stack m_stack;
    Gtk::Button *m_backButton{nullptr};
    Gtk::Button *m_primaryButton{nullptr};
    Gtk::MenuButton *m_menuButton{nullptr};

    Gtk::Revealer m_noticeRevealer;
    Gtk::Box m_noticeBox;
    Gtk::Label m_notice;
    sigc::connection m_noticeTimer;

    BasePage *m_basePage{nullptr};
    std::vector<ModulePage *> m_modulePages;
    OptionalPage *m_optionalPage{nullptr};
    ReviewPage *m_reviewPage{nullptr};

    std::unique_ptr<ThemeWatcher> m_theme;
    std::unique_ptr<HelpWindow> m_help;
    std::unique_ptr<Gtk::AboutDialog> m_about;
    std::unique_ptr<BuildConsole> m_console;
    AsyncTask<std::pair<bool, std::string>> m_generate;
    bool m_altTapped{false};
    bool m_syncing{false};
};

} // namespace kineticos
