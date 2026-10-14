#include "ui/window.h"

#include "core/dcli.h"
#include "core/workspace.h"
#include "ui/buildconsole.h"
#include "ui/helpwindow.h"
#include "ui/pages.h"
#include "ui/themewatcher.h"

#include <gdk/gdkkeysyms.h>
#include <gdkmm/texture.h>
#include <giomm/actiongroup.h>
#include <giomm/menu.h>
#include <giomm/simpleaction.h>
#include <glibmm/main.h>
#include <gtkmm/alertdialog.h>
#include <gtkmm/box.h>
#include <gtkmm/eventcontrollerkey.h>
#include <gtkmm/image.h>
#include <gtkmm/overlay.h>
#include <gtkmm/separator.h>

#include <algorithm>
#include <exception>
#include <functional>

namespace kineticos {

namespace {

bool isAlt(const guint keyval)
{
    return keyval == GDK_KEY_Alt_L || keyval == GDK_KEY_Alt_R;
}

// Privileged operations go through pkexec and our allow-listed helper, so the system polkit
// agent (Noctalia) shows the branded authentication dialog.
const char *const kPkexec = "/usr/bin/pkexec";
const char *const kHelper =
    "/usr/libexec/kinetic-configurator/kinetic-configurator-helper";

void errorDialog(Gtk::Window &parent, const std::string &message, const std::string &detail)
{
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message(message);
    if (!detail.empty())
        dialog->set_detail(detail);
    dialog->show(parent);
}

void confirm(Gtk::Window &parent, const std::string &message, const std::string &detail,
             const std::string &confirmLabel, const std::string &cancelLabel,
             std::function<void(bool)> done)
{
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message(message);
    dialog->set_detail(detail);
    dialog->set_buttons({cancelLabel, confirmLabel});
    dialog->set_cancel_button(0);
    dialog->set_default_button(1);
    dialog->choose(parent, [dialog, done = std::move(done)](
                               const Glib::RefPtr<Gio::AsyncResult> &result) {
        done(dialog->choose_finish(result) == 1);
    });
}

} // namespace

Window::Window(const Glib::RefPtr<Gtk::Application> &application, std::string root,
               Settings settings)
    : m_root(std::move(root))
    , m_settings(settings)
    , m_profile(m_root)
    , m_content(Gtk::Orientation::VERTICAL)
    , m_body(Gtk::Orientation::VERTICAL)
    , m_noticeBox(Gtk::Orientation::HORIZONTAL)
{
    set_application(application);
    set_title("KineticOS Configurator");
    set_icon_name("kinetic-configurator");
    set_default_size(820, 640);

    m_baseDescriptions = {
        {"ghcr.io/theblack-don/kineticos:default", "AMD and Intel GPUs"},
        {"ghcr.io/theblack-don/kineticos:nvidia",
         "NVIDIA GPUs based on Turing or newer: GTX 16 series, and RTX 20, 30, 40 and 50 "
         "series"},
        {"ghcr.io/theblack-don/kineticos:nvidia-legacy",
         "NVIDIA GPUs older than the 10 series"},
        {"ghcr.io/theblack-don/kineticos:deck",
         "Very early; not recommended for normal use."},
    };

    m_modules = loadModules(m_root);
    std::set<std::string> moduleNames;
    for (const auto &[name, module] : m_modules)
        moduleNames.insert(name);
    m_profile.ensureModules(moduleNames);

    m_selection.baseImage = m_profile.baseImage();
    for (const ProfileEntry &entry : m_profile.entries()) {
        if (entry.name == "base")
            continue;
        const auto found = m_modules.find(entry.name);
        if (found == m_modules.end())
            continue;
        const Module &module = found->second;
        if (module.apps.empty())
            continue;
        m_selection.appModules.insert(entry.name);
        std::set<std::string> selected;
        std::set<std::string> removals;
        for (const App &app : module.apps) {
            if (app.enabled)
                selected.insert(app.name);
            if (app.section == "remove")
                removals.insert(app.name);
        }
        if (!selected.empty())
            m_selection.apps[entry.name] = selected;
        if (!removals.empty())
            m_selection.removalApps[entry.name] = removals;
    }
    if (const auto browsers = m_modules.find("browsers"); browsers != m_modules.end()) {
        m_selection.braveRepoEnabled = repoCommandEnabled(&browsers->second, "brave");
        m_selection.vivaldiRepoEnabled = repoCommandEnabled(&browsers->second, "vivaldi");
    }

    m_theme = std::make_unique<ThemeWatcher>(*this);
    buildHeader();
    buildBody();
    buildActions(application);
    applyTitleBar(m_settings.systemTitleBar());
    watchAltTap(*this);
    if (m_menuButton != nullptr && m_menuButton->get_popover())
        watchAltTap(*m_menuButton->get_popover());
    go(0);
}

Window::~Window() = default;

void Window::buildHeader()
{
    m_header.set_title_widget(*Gtk::make_managed<Gtk::Box>());

    auto *brand = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::HORIZONTAL, 10);
    auto *icon = Gtk::make_managed<Gtk::Image>(
        Gdk::Texture::create_from_resource("/com/weecraglinux/kinetic/kinetic-configurator.png"));
    icon->set_pixel_size(28);
    brand->append(*icon);
    auto *wordmark = Gtk::make_managed<Gtk::Label>("KINETICOS CONFIGURATOR");
    wordmark->add_css_class("wordmark");
    brand->append(*wordmark);
    brand->set_margin_end(12);
    m_header.pack_start(*brand);

    m_backButton = Gtk::make_managed<Gtk::Button>("Back");
    m_backButton->set_tooltip_text("Return to the previous step");
    m_backButton->signal_clicked().connect([this] { onBack(); });

    auto menu = Gio::Menu::create();
    auto view = Gio::Menu::create();
    view->append("Use System Title Bar", "win.system-title-bar");
    menu->append_section(view);
    auto help = Gio::Menu::create();
    help->append("Help", "win.help");
    help->append("About KineticOS Configurator", "win.about");
    menu->append_section(help);
    auto quit = Gio::Menu::create();
    quit->append("Quit", "app.quit");
    menu->append_section(quit);

    m_menuButton = Gtk::make_managed<Gtk::MenuButton>();
    m_menuButton->set_icon_name("open-menu-symbolic");
    m_menuButton->set_menu_model(menu);
    m_menuButton->set_tooltip_text("Main menu");
    m_menuButton->set_primary(true);
    m_header.pack_end(*m_menuButton);

    m_primaryButton = Gtk::make_managed<Gtk::Button>("Next");
    m_primaryButton->add_css_class("kc-primary");
    m_primaryButton->add_css_class("suggested-action");
    m_primaryButton->signal_clicked().connect([this] { onPrimary(); });
    m_header.pack_end(*m_primaryButton);

    // Back sits immediately left of Next on the right-hand side.
    m_header.pack_end(*m_backButton);
}

void Window::buildBody()
{
    m_basePage = Gtk::make_managed<BasePage>(*this);
    m_stack.add(*m_basePage, "base");

    for (const ProfileEntry &entry : m_profile.entries()) {
        if (entry.name == "base")
            continue;
        const auto found = m_modules.find(entry.name);
        if (found == m_modules.end() || found->second.apps.empty())
            continue;
        auto *page = Gtk::make_managed<ModulePage>(*this, found->second);
        m_stack.add(*page, "module-" + entry.name);
        m_modulePages.push_back(page);
    }

    m_optionalPage = Gtk::make_managed<OptionalPage>(*this);
    m_stack.add(*m_optionalPage, "optional");
    m_reviewPage = Gtk::make_managed<ReviewPage>(*this);
    m_stack.add(*m_reviewPage, "review");

    m_notice.set_wrap(true);
    m_notice.set_max_width_chars(80);
    m_noticeBox.add_css_class("kc-notice");
    m_noticeBox.append(m_notice);
    m_noticeRevealer.set_child(m_noticeBox);
    m_noticeRevealer.set_transition_type(Gtk::RevealerTransitionType::SLIDE_UP);
    m_noticeRevealer.set_halign(Gtk::Align::CENTER);
    m_noticeRevealer.set_valign(Gtk::Align::END);
    m_noticeRevealer.set_can_target(false);

    auto *overlay = Gtk::make_managed<Gtk::Overlay>();
    overlay->set_child(m_stack);
    overlay->add_overlay(m_noticeRevealer);
    overlay->set_vexpand(true);

    m_body.append(*overlay);
    m_body.set_vexpand(true);
    m_content.append(m_body);
    m_content.set_vexpand(true);
    set_child(m_content);
}

void Window::buildActions(const Glib::RefPtr<Gtk::Application> &application)
{
    add_action("help", [this] { showHelp(); });
    add_action("about", [this] { showAbout(); });

    auto titleBar = add_action_bool("system-title-bar", false);
    titleBar->signal_activate().connect([titleBar](const Glib::VariantBase &) {
        bool system = false;
        titleBar->get_state(system);
        titleBar->change_state(!system);
    });
    titleBar->signal_change_state().connect([this, titleBar](const Glib::VariantBase &value) {
        const bool system = Glib::VariantBase::cast_dynamic<Glib::Variant<bool>>(value).get();
        titleBar->set_state(value);
        m_settings.setSystemTitleBar(system);
        applyTitleBar(system);
    });
    titleBar->set_state(Glib::Variant<bool>::create(m_settings.systemTitleBar()));

    application->set_accel_for_action("win.help", "F1");
    application->set_accel_for_action("win.system-title-bar", "<Control><Shift>m");
    application->set_accel_for_action("app.quit", "<Control>q");
}

void Window::applyTitleBar(const bool system)
{
    const bool realized = get_realized();
    const auto application = get_application();
    if (realized) {
        application->hold();
        set_visible(false);
        Gtk::Widget::unrealize();
    }
    if (system) {
        unset_titlebar();
        m_header.set_show_title_buttons(false);
        m_content.prepend(m_header);
    } else {
        if (m_header.get_parent())
            m_content.remove(m_header);
        m_header.set_show_title_buttons(true);
        set_titlebar(m_header);
    }
    if (realized) {
        set_application(application);
        present();
        focusPrimary();
        application->release();
    }
}

std::vector<Gtk::Widget *> Window::flow() const
{
    std::vector<Gtk::Widget *> pages;
    pages.push_back(m_basePage);
    for (ModulePage *page : m_modulePages)
        pages.push_back(page);
    if (!questions(m_selection).empty())
        pages.push_back(m_optionalPage);
    pages.push_back(m_reviewPage);
    return pages;
}

int Window::currentIndex()
{
    const std::vector<Gtk::Widget *> pages = flow();
    Gtk::Widget *current = m_stack.get_visible_child();
    const auto found = std::find(pages.begin(), pages.end(), current);
    return found == pages.end() ? 0 : static_cast<int>(found - pages.begin());
}

void Window::go(const int index)
{
    const std::vector<Gtk::Widget *> pages = flow();
    const int clamped = std::max(0, std::min(index, static_cast<int>(pages.size()) - 1));
    Gtk::Widget *page = pages[static_cast<std::size_t>(clamped)];
    m_stack.set_visible_child(*page);
    if (page == static_cast<Gtk::Widget *>(m_optionalPage))
        m_optionalPage->refresh();
    if (page == static_cast<Gtk::Widget *>(m_reviewPage))
        m_reviewPage->refresh();
    m_primaryButton->set_label(clamped == static_cast<int>(pages.size()) - 1
                                   ? "Write changes"
                                   : "Next");
    m_backButton->set_sensitive(clamped > 0);
    Glib::signal_idle().connect_once([this] { focusPrimary(); });
}

void Window::refreshFlow()
{
    const std::vector<Gtk::Widget *> pages = flow();
    Gtk::Widget *current = m_stack.get_visible_child();
    if (std::find(pages.begin(), pages.end(), current) == pages.end()) {
        go(currentIndex());
        return;
    }
    const int index = currentIndex();
    m_primaryButton->set_label(index == static_cast<int>(pages.size()) - 1
                                   ? "Write changes"
                                   : "Next");
    m_backButton->set_sensitive(index > 0);
}

void Window::onBack()
{
    go(currentIndex() - 1);
}

void Window::onPrimary()
{
    const int index = currentIndex();
    if (index < static_cast<int>(flow().size()) - 1)
        go(index + 1);
    else
        writeAndBuild();
}

void Window::focusPrimary()
{
    Gtk::Widget *page = m_stack.get_visible_child();
    Gtk::Widget *input = nullptr;
    if (page == static_cast<Gtk::Widget *>(m_basePage))
        input = m_basePage->primaryInput();
    else if (page == static_cast<Gtk::Widget *>(m_optionalPage))
        input = m_optionalPage->primaryInput();
    else if (page == static_cast<Gtk::Widget *>(m_reviewPage))
        input = m_reviewPage->primaryInput();
    else
        for (ModulePage *module : m_modulePages)
            if (page == static_cast<Gtk::Widget *>(module))
                input = module->primaryInput();
    if (input != nullptr && input->get_visible())
        input->grab_focus();
}

void Window::showHelp()
{
    if (!m_help)
        m_help = std::make_unique<HelpWindow>(*this);
    m_help->setMonoFamily(m_theme->monoFamily());
    m_help->present();
}

void Window::showAbout()
{
    if (!m_about) {
        m_about = std::make_unique<Gtk::AboutDialog>();
        m_about->set_transient_for(*this);
        m_about->set_modal(true);
        m_about->set_hide_on_close(true);
        m_about->set_program_name("KineticOS Configurator");
        m_about->set_version(KINETIC_CONFIGURATOR_VERSION);
        m_about->set_comments(
            "Clone, configure, update, reset, and build a KineticOS image project.\n\n"
            "Built with GTK 4.");
        m_about->set_website("https://github.com/WeeCragLinux/KineticOS-Configurator");
        m_about->set_website_label("Project page and issue tracker");
        m_about->set_authors({"WeeCragLinux"});
        m_about->set_license_type(Gtk::License::MIT_X11);
        m_about->set_logo(
            Gdk::Texture::create_from_resource("/com/weecraglinux/kinetic/kinetic-configurator.png"));
    }
    m_about->present();
}

void Window::showSameImageDialog()
{
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message("This image is the same as the one you are running");
    dialog->set_detail(
        "The image you just built matches the deployment this computer is currently booted "
        "from, so switching and rebooting would change nothing.\n\n"
        "Change your selections in the wizard (for example, add or remove an app, or pick a "
        "different base image) and build again, or exit the configurator.");
    dialog->set_buttons({"Go back and make changes", "Exit"});
    // Returning to the wizard is the safe answer, so it is the default and what Escape picks.
    dialog->set_cancel_button(0);
    dialog->set_default_button(0);
    dialog->choose(*this, [this, dialog](const Glib::RefPtr<Gio::AsyncResult> &result) {
        if (dialog->choose_finish(result) == 1) {
            if (const auto application = get_application())
                application->activate_action("quit");
            return;
        }
        go(0);
    });
}

void Window::notify(const std::string &text, const NoticeKind kind, const unsigned int timeoutMs)
{
    for (const char *name : {"positive", "neutral", "negative"})
        m_noticeBox.remove_css_class(name);
    switch (kind) {
    case NoticeKind::Positive:
        m_noticeBox.add_css_class("positive");
        break;
    case NoticeKind::Neutral:
        m_noticeBox.add_css_class("neutral");
        break;
    case NoticeKind::Negative:
        m_noticeBox.add_css_class("negative");
        break;
    case NoticeKind::Info:
        break;
    }
    m_notice.set_text(text);
    m_noticeRevealer.set_reveal_child(true);
    m_noticeTimer.disconnect();
    if (timeoutMs > 0)
        m_noticeTimer = Glib::signal_timeout().connect(
            [this] {
                m_noticeRevealer.set_reveal_child(false);
                return false;
            },
            timeoutMs);
}

void Window::watchAltTap(Gtk::Widget &widget)
{
    auto keys = Gtk::EventControllerKey::create();
    keys->set_propagation_phase(Gtk::PropagationPhase::CAPTURE);
    keys->signal_key_pressed().connect(
        [this](guint keyval, guint, Gdk::ModifierType) {
            m_altTapped = isAlt(keyval);
            return false;
        },
        false);
    keys->signal_key_released().connect([this](guint keyval, guint, Gdk::ModifierType) {
        if (m_altTapped && isAlt(keyval)) {
            if (m_menuButton->get_active()) {
                m_menuButton->popdown();
                Glib::signal_idle().connect_once([this] { focusPrimary(); });
            } else {
                m_menuButton->popup();
            }
        }
        m_altTapped = false;
    });
    widget.add_controller(keys);
}

void Window::writeAndBuild()
{
    // Ignore repeated clicks while a write/generate run is already in flight, so only one
    // "Build image now?" prompt is ever produced.
    if (m_writing)
        return;
    try {
        apply(m_root, m_selection, m_modules, m_profile);
    } catch (const std::exception &error) {
        errorDialog(*this, "Could not write files", error.what());
        return;
    }

    m_writing = true;
    notify("Writing the project configuration…", NoticeKind::Info, 0);
    m_generate.start(
        [root = m_root] { return generate(root); },
        [this](std::pair<bool, std::string> result) {
            m_writing = false;
            if (!result.first) {
                notify("dcli-bootc gen failed.", NoticeKind::Negative, 0);
                errorDialog(*this, "Files written, but dcli-bootc gen failed",
                            result.second.empty() ? "dcli-bootc gen failed." : result.second);
                return;
            }
            notify("Files written and dcli-bootc gen completed.", NoticeKind::Positive, 5000);
            confirm(
                *this, "Build image now?",
                "Would you like to run dcli-bootc build for this project now?", "Build",
                "Not now", [this](bool yes) {
                    if (!yes)
                        return;
                    m_console = std::make_unique<BuildConsole>(
                        *this, "Building KineticOS image",
                        std::vector<std::string>{kPkexec, kHelper, "build", "--project",
                                                 m_root});
                    m_console->signalFinished().connect([this](bool success) {
                        const std::string text = m_console ? m_console->output() : std::string();
                        if (m_console)
                            m_console->close();
                        if (!success) {
                            errorDialog(*this, "Image build failed",
                                        "dcli-bootc build did not complete successfully.\n\n"
                                            + (text.size() > 4000 ? text.substr(text.size() - 4000)
                                                                  : text));
                            return;
                        }
                        // dcli-bootc already compared the built digest with the booted one and
                        // reported a match. Switching would be a no-op, so do not offer it.
                        if (buildReportedIdenticalImage(text)) {
                            showSameImageDialog();
                            return;
                        }
                        confirm(
                            *this, "Switch to the new image and reboot?",
                            "The image built successfully. Switch this computer to the new "
                            "image and reboot now?\n\nThe current deployment should remain "
                            "available for rollback.",
                            "Switch and reboot", "Not now", [this](bool switchNow) {
                                if (!switchNow)
                                    return;
                                m_console = std::make_unique<BuildConsole>(
                                    *this, "Switching to the new image",
                                    std::vector<std::string>{kPkexec, kHelper, "switch",
                                                             "--project", m_root});
                                m_console->signalFinished().connect([this](bool ok) {
                                    const std::string text =
                                        m_console ? m_console->output() : std::string();
                                    if (m_console)
                                        m_console->close();
                                    if (!ok) {
                                        errorDialog(
                                            *this, "Could not switch image",
                                            "dcli-bootc switch did not complete successfully. "
                                            "Check its output and your system's bootc "
                                            "permissions.\n\n"
                                                + (text.size() > 4000
                                                       ? text.substr(text.size() - 4000)
                                                       : text));
                                        return;
                                    }
                                    // Safety net: if the switch turned out to stage nothing new,
                                    // report the identical image rather than claiming a switch.
                                    if (switchReportedNothingStaged(text)) {
                                        showSameImageDialog();
                                        return;
                                    }
                                    notify("Switching to the new image.", NoticeKind::Neutral, 0);
                                });
                                m_console->present();
                                m_console->run();
                            });
                    });
                    m_console->present();
                    m_console->run();
                });
        });
}

} // namespace kineticos
