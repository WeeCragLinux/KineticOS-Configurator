#include "ui/chooser.h"

#include "core/process.h"

#include <gdkmm/texture.h>
#include <giomm/file.h>
#include <glibmm/fileutils.h>
#include <glibmm/miscutils.h>
#include <gtkmm/alertdialog.h>
#include <gtkmm/button.h>
#include <gtkmm/filedialog.h>
#include <gtkmm/headerbar.h>
#include <gtkmm/image.h>
#include <gtkmm/label.h>

namespace kineticos {

namespace {

Gtk::Button *makeButton(const std::string &text, const bool primary = false)
{
    auto *button = Gtk::make_managed<Gtk::Button>(text);
    if (primary) {
        button->add_css_class("kc-primary");
        button->add_css_class("suggested-action");
    }
    button->set_hexpand(true);
    return button;
}

void errorDialog(Gtk::Window &parent, const std::string &message, const std::string &detail)
{
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message(message);
    if (!detail.empty())
        dialog->set_detail(detail);
    dialog->show(parent);
}

void infoDialog(Gtk::Window &parent, const std::string &message, const std::string &detail)
{
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message(message);
    if (!detail.empty())
        dialog->set_detail(detail);
    dialog->show(parent);
}

} // namespace

ChooserWindow::ChooserWindow(const Glib::RefPtr<Gtk::Application> &application, Settings settings)
    : m_settings(settings)
    , m_body(Gtk::Orientation::VERTICAL, 10)
{
    // Attach the window to the application so Gtk::Application keeps running while the
    // chooser is the only window (otherwise it quits as soon as activate() returns).
    set_application(application);
    m_saved = m_settings.checkoutPath();
    build();
}

ChooserWindow::~ChooserWindow() = default;

void ChooserWindow::build()
{
    set_title("Choose project");
    set_icon_name("kinetic-configurator");
    set_default_size(680, 500);

    auto *header = Gtk::make_managed<Gtk::HeaderBar>();
    auto *brand = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::HORIZONTAL, 10);
    auto *icon = Gtk::make_managed<Gtk::Image>(
        Gdk::Texture::create_from_resource("/com/weecraglinux/kinetic/kinetic-configurator.png"));
    icon->set_pixel_size(28);
    brand->append(*icon);
    auto *wordmark = Gtk::make_managed<Gtk::Label>("KINETICOS CONFIGURATOR");
    wordmark->add_css_class("wordmark");
    brand->append(*wordmark);
    brand->set_margin_end(12);
    header->pack_start(*brand);
    header->set_title_widget(*Gtk::make_managed<Gtk::Box>());
    set_titlebar(*header);

    m_body.add_css_class("body");
    m_body.append(*Gtk::make_managed<Gtk::Label>(
        "Choose a project to configure, or clone a fresh copy. Projects stay in a writable "
        "folder you control."));

    if (!m_saved.empty() && isProject(m_saved)) {
        auto *card = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::VERTICAL, 8);
        card->add_css_class("kc-card");
        auto *savedLabel = Gtk::make_managed<Gtk::Label>("SAVED PROJECT");
        savedLabel->add_css_class("section-label");
        savedLabel->set_halign(Gtk::Align::START);
        card->append(*savedLabel);
        auto *pathLabel = Gtk::make_managed<Gtk::Label>(m_saved);
        pathLabel->add_css_class("mono");
        pathLabel->set_halign(Gtk::Align::START);
        pathLabel->set_wrap(true);
        card->append(*pathLabel);

        auto *openSaved = makeButton("Open saved project", true);
        openSaved->signal_clicked().connect([this] { finishWith(m_saved); });
        card->append(*openSaved);

        auto *update = makeButton("Update full template, keep my choices…");
        update->signal_clicked().connect([this] { confirmUpdate(); });
        card->append(*update);

        auto *reset = makeButton("Reset project to a fresh template…");
        reset->signal_clicked().connect([this] { confirmReset(); });
        card->append(*reset);
        m_body.append(*card);
    }

    auto *actions = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::HORIZONTAL, 8);
    auto *clone = makeButton("Clone image project…");
    clone->signal_clicked().connect([this] { chooseClone(); });
    actions->append(*clone);
    auto *existing = makeButton("Open an existing project…");
    existing->signal_clicked().connect([this] { chooseExisting(); });
    actions->append(*existing);
    m_body.append(*actions);

    auto *footer = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::HORIZONTAL, 8);
    footer->set_halign(Gtk::Align::END);
    auto *cancel = Gtk::make_managed<Gtk::Button>("Cancel");
    cancel->signal_clicked().connect([this] { close(); });
    footer->append(*cancel);
    m_body.append(*footer);

    auto *root = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::VERTICAL);
    root->append(m_body);
    set_child(*root);
}

void ChooserWindow::finishWith(const std::string &path)
{
    if (!isProject(path)) {
        errorDialog(*this, "Project not found",
                    "That folder is not a valid image project.");
        return;
    }
    const std::string resolved = Gio::File::create_for_path(path)->get_path();
    m_settings.setCheckoutPath(resolved);
    m_chosen.emit(resolved);
    close();
}

void ChooserWindow::chooseExisting()
{
    auto dialog = Gtk::FileDialog::create();
    dialog->set_title("Open image project");
    const std::string initial =
        (!m_saved.empty() && Glib::file_test(m_saved, Glib::FileTest::IS_DIR))
            ? m_saved
            : Glib::get_home_dir();
    dialog->set_initial_folder(Gio::File::create_for_path(initial));
    dialog->select_folder(*this, [this, dialog](const Glib::RefPtr<Gio::AsyncResult> &result) {
        try {
            auto file = dialog->select_folder_finish(result);
            if (!file)
                return;
            const std::string path = file->get_path();
            if (!isProject(path)) {
                errorDialog(*this, "Not an image project",
                            "Choose a folder containing profile.yaml and a modules/ "
                            "directory.");
                return;
            }
            finishWith(path);
        } catch (const Glib::Error &) {
            // Cancelled.
        }
    });
}

void ChooserWindow::chooseClone()
{
    if (!programOnPath("git")) {
        errorDialog(*this, "Git is required", "Install Git before cloning an image project.");
        return;
    }
    auto dialog = Gtk::FileDialog::create();
    dialog->set_title("Choose where to store the image project");
    const std::string projects = Glib::build_filename(Glib::get_home_dir(), "Projects");
    dialog->set_initial_folder(
        Gio::File::create_for_path(Glib::file_test(projects, Glib::FileTest::IS_DIR)
                                       ? projects
                                       : Glib::get_home_dir()));
    dialog->select_folder(*this, [this, dialog](const Glib::RefPtr<Gio::AsyncResult> &result) {
        try {
            auto file = dialog->select_folder_finish(result);
            if (!file)
                return;
            const std::string parent = file->get_path();
            runGit("clone", Glib::build_filename(parent, kProjectDirectory));
        } catch (const Glib::Error &) {
        }
    });
}

void ChooserWindow::confirmUpdate()
{
    if (m_saved.empty())
        return;
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message("Update the full project template?");
    dialog->set_detail(
        "This replaces the selected project with a fresh upstream clone. The current base "
        "image, module, app, and list-item choices will be reapplied where those entries "
        "still exist. Manual edits to scripts and other files will be replaced.\n\nA complete "
        "backup of the current folder will be created beside it first. Continue?");
    dialog->set_buttons({"Cancel", "Update"});
    dialog->set_cancel_button(0);
    dialog->set_default_button(1);
    dialog->choose(*this, [this, dialog](const Glib::RefPtr<Gio::AsyncResult> &result) {
        if (dialog->choose_finish(result) == 1)
            runGit("update", m_saved);
    });
}

void ChooserWindow::confirmReset()
{
    if (m_saved.empty())
        return;
    auto dialog = Gtk::AlertDialog::create();
    dialog->set_modal(true);
    dialog->set_message("Reset project to a fresh template?");
    dialog->set_detail(
        "This replaces the selected project with a fresh upstream clone and discards all "
        "current choices and local edits. A complete backup of the current folder will be "
        "created beside it first. Continue?");
    dialog->set_buttons({"Cancel", "Reset"});
    dialog->set_cancel_button(0);
    dialog->set_default_button(1);
    dialog->choose(*this, [this, dialog](const Glib::RefPtr<Gio::AsyncResult> &result) {
        if (dialog->choose_finish(result) == 1)
            runGit("reset", m_saved);
    });
}

void ChooserWindow::runGit(const std::string &operation, const std::string &path)
{
    showBusy(operation == "clone" ? "Cloning the image project…"
                                  : (operation == "reset" ? "Resetting the project…"
                                                          : "Updating the project…"));
    m_task.start(
        [operation, path]() -> GitResult {
            if (operation == "clone")
                return cloneProject(path);
            if (operation == "reset")
                return resetProject(path);
            return updateProject(path);
        },
        [this, operation](GitResult result) {
            hideBusy();
            if (!result.ok) {
                errorDialog(*this, "Project operation failed", result.detail);
                return;
            }
            if (operation == "reset" || operation == "update")
                infoDialog(*this,
                           operation == "reset" ? "Project reset" : "Project updated",
                           result.detail);
            finishWith(result.checkout);
        });
}

void ChooserWindow::showBusy(const std::string &message)
{
    if (!m_busy) {
        m_busy = std::make_unique<Gtk::Window>();
        m_busy->set_transient_for(*this);
        m_busy->set_modal(true);
        m_busy->set_decorated(false);
        m_busy->set_default_size(320, 100);
        auto *box = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::HORIZONTAL, 12);
        box->add_css_class("dialog-body");
        m_busySpinner = Gtk::make_managed<Gtk::Spinner>();
        box->append(*m_busySpinner);
        m_busyLabel = Gtk::make_managed<Gtk::Label>();
        m_busyLabel->set_wrap(true);
        box->append(*m_busyLabel);
        m_busy->set_child(*box);
    }
    m_busyLabel->set_text(message);
    m_busySpinner->start();
    m_busy->present();
}

void ChooserWindow::hideBusy()
{
    if (m_busy != nullptr) {
        m_busySpinner->stop();
        m_busy->set_visible(false);
    }
}

} // namespace kineticos
