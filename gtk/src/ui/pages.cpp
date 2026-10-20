#include "ui/pages.h"

#include "ui/window.h"

#include <glibmm/markup.h>
#include <gtkmm/label.h>
#include <gtkmm/scrolledwindow.h>
#include <gtkmm/separator.h>

#include <algorithm>
#include <cctype>
#include <sstream>

namespace kineticos {

namespace {

std::string uppercase(std::string text)
{
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    return text;
}

std::string titleCase(std::string text)
{
    if (!text.empty())
        text[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(text[0])));
    return text;
}

Gtk::Label *sectionLabel(const std::string &text)
{
    auto *label = Gtk::make_managed<Gtk::Label>(uppercase(text));
    label->add_css_class("section-label");
    label->set_halign(Gtk::Align::START);
    return label;
}

Gtk::Label *heading(const std::string &text)
{
    auto *label = Gtk::make_managed<Gtk::Label>();
    label->set_markup("<span size=\"large\" weight=\"bold\">" + Glib::Markup::escape_text(text)
                      + "</span>");
    label->set_halign(Gtk::Align::START);
    label->set_wrap(true);
    return label;
}

Gtk::Label *muted(const std::string &text)
{
    auto *label = Gtk::make_managed<Gtk::Label>(text);
    label->add_css_class("muted");
    label->set_halign(Gtk::Align::START);
    label->set_wrap(true);
    return label;
}

std::string summary(Window &window)
{
    const Selection &state = window.selection();
    std::ostringstream out;
    out << "Base image: " << state.baseImage << "\n\n";
    for (const ProfileEntry &entry : resolve(window.profile(), state)) {
        if (!entry.enabled) {
            out << "off   " << entry.name << "\n";
            continue;
        }
        std::set<std::string> selected;
        if (const auto found = state.apps.find(entry.name); found != state.apps.end())
            selected = found->second;
        std::set<std::string> removals;
        if (const auto module = window.modules().find(entry.name);
            module != window.modules().end()) {
            for (const App &app : module->second.apps)
                if (app.section == "remove")
                    removals.insert(app.name);
        }
        std::vector<std::string> display;
        for (const std::string &name : selected)
            display.push_back(removals.count(name) != 0 ? "remove " + name : name);
        out << "on    " << entry.name << ": ";
        if (display.empty())
            out << "default";
        else
            for (std::size_t i = 0; i < display.size(); ++i)
                out << (i == 0 ? "" : ", ") << display[i];
        out << "\n";
    }
    return out.str();
}

} // namespace

std::string appLabel(const App &app)
{
    if (app.section == "remove")
        return "Remove " + app.name;
    if (app.section == "flatpaks")
        return app.name + "  (Flatpak, installed per user)";
    if (app.section == "local_rpms")
        return app.name + "  (local RPM)";
    if (rpmfusionApps().count(app.name) != 0)
        return app.name + "  (needs RPM Fusion)";
    return app.name;
}

// --- base image ---------------------------------------------------------------

BasePage::BasePage(Window &window)
    : Gtk::Box(Gtk::Orientation::VERTICAL, 12)
    , m_window(window)
{
    add_css_class("body");
    append(*sectionLabel("Base image"));
    append(*heading("Welcome to KineticOS Image Configurator"));
    append(*muted("This wizard configures and builds your Kineticos image. Choose the base "
                  "image that matches your GPU."));

    Gtk::CheckButton *group = nullptr;
    for (const std::string &ref : baseImages()) {
        auto *radio = Gtk::make_managed<Gtk::CheckButton>(ref);
        if (group == nullptr)
            group = radio;
        else
            radio->set_group(*group);
        radio->set_active(m_window.selection().baseImage == ref);
        radio->signal_toggled().connect([this, radio, ref] {
            if (radio->get_active()) {
                m_window.selection().baseImage = ref;
                m_window.refreshFlow();
            }
        });
        append(*radio);
        if (m_first == nullptr)
            m_first = radio;

        const auto &descriptions = m_window.baseDescriptions();
        if (const auto found = descriptions.find(ref); found != descriptions.end()) {
            auto *note = muted(found->second);
            note->set_margin_start(24);
            append(*note);
        }
    }
}

Gtk::Widget *BasePage::primaryInput() const
{
    return m_first;
}

// --- module -------------------------------------------------------------------

ModulePage::ModulePage(Window &window, const Module &module)
    : Gtk::Box(Gtk::Orientation::VERTICAL, 12)
    , m_window(window)
    , m_name(module.name)
{
    add_css_class("body");
    m_removal = !module.apps.empty()
        && std::all_of(module.apps.begin(), module.apps.end(),
                       [](const App &app) { return app.section == "remove"; });

    append(*sectionLabel(m_name));
    append(*heading(m_removal ? "Packages to remove" : titleCase(module.name)));
    append(*muted(m_removal ? "Choose preinstalled packages to remove from your image."
                            : "Choose the software to include in your image."));

    auto *scroller = Gtk::make_managed<Gtk::ScrolledWindow>();
    scroller->set_policy(Gtk::PolicyType::NEVER, Gtk::PolicyType::AUTOMATIC);
    scroller->set_vexpand(true);
    auto *card = Gtk::make_managed<Gtk::Box>(Gtk::Orientation::VERTICAL, 10);
    card->add_css_class("kc-card");
    if (!module.description.empty())
        card->append(*muted(module.description));

    std::set<std::string> chosen;
    if (const auto found = m_window.selection().apps.find(m_name);
        found != m_window.selection().apps.end())
        chosen = found->second;

    for (const App &app : module.apps) {
        auto *box = Gtk::make_managed<Gtk::CheckButton>(appLabel(app));
        box->set_active(chosen.count(app.name) != 0);
        box->signal_toggled().connect([this] { sync(); });
        card->append(*box);
        m_boxes.emplace_back(app, box);
    }
    scroller->set_child(*card);
    append(*scroller);
}

void ModulePage::sync()
{
    std::set<std::string> selected;
    for (const auto &[app, box] : m_boxes)
        if (box->get_active())
            selected.insert(app.name);
    if (m_window.selection().removalApps.count(m_name) != 0)
        m_window.selection().disableRemovals = false;
    if (selected.empty())
        m_window.selection().apps.erase(m_name);
    else
        m_window.selection().apps[m_name] = std::move(selected);
}

Gtk::Widget *ModulePage::primaryInput() const
{
    return m_boxes.empty() ? nullptr : static_cast<Gtk::Widget *>(m_boxes.front().second);
}

// --- optional repositories ----------------------------------------------------

OptionalPage::OptionalPage(Window &window)
    : Gtk::Box(Gtk::Orientation::VERTICAL, 12)
    , m_window(window)
{
    add_css_class("body");
    append(*sectionLabel("Optional repositories"));
    append(*heading("Optional repositories and removals"));
    append(*muted("Keep these repositories enabled, or disable ones that no selected app "
                  "needs."));

    const auto add = [this](Gtk::CheckButton *&target, const std::string &text) {
        target = Gtk::make_managed<Gtk::CheckButton>(text);
        append(*target);
    };
    add(m_rpm, "Disable RPM Fusion (free and nonfree repos)");
    add(m_removals, "Disable the selected package removals");
    add(m_brave, "Disable the Brave browser repository");
    add(m_vivaldi, "Disable the Vivaldi repository");

    m_rpm->signal_toggled().connect(
        [this] { m_window.selection().disableRpmfusion = m_rpm->get_active(); });
    m_removals->signal_toggled().connect(
        [this] { m_window.selection().disableRemovals = m_removals->get_active(); });
    m_brave->signal_toggled().connect(
        [this] { m_window.selection().disableBraveRepo = m_brave->get_active(); });
    m_vivaldi->signal_toggled().connect(
        [this] { m_window.selection().disableVivaldiRepo = m_vivaldi->get_active(); });
}

void OptionalPage::refresh()
{
    const std::vector<std::string> asked = questions(m_window.selection());
    const auto askedContains = [&asked](const std::string &name) {
        return std::find(asked.begin(), asked.end(), name) != asked.end();
    };
    Selection &state = m_window.selection();
    m_rpm->set_active(state.disableRpmfusion);
    m_rpm->set_visible(askedContains("rpmfusion"));
    m_removals->set_active(state.disableRemovals);
    m_removals->set_visible(askedContains("removals"));
    m_brave->set_active(state.disableBraveRepo);
    m_brave->set_visible(askedContains("brave"));
    m_vivaldi->set_active(state.disableVivaldiRepo);
    m_vivaldi->set_visible(askedContains("vivaldi"));
}

Gtk::Widget *OptionalPage::primaryInput() const
{
    for (Gtk::CheckButton *box : {m_rpm, m_removals, m_brave, m_vivaldi})
        if (box->get_visible())
            return box;
    return nullptr;
}

// --- review -------------------------------------------------------------------

ReviewPage::ReviewPage(Window &window)
    : Gtk::Box(Gtk::Orientation::VERTICAL, 12)
    , m_window(window)
    , m_buffer(Gtk::TextBuffer::create())
{
    add_css_class("body");
    append(*sectionLabel("Review"));
    append(*heading("Review"));
    append(*muted("These changes are written to profile.yaml and modules/*.yaml, then "
                  "dcli-bootc gen runs. You can build the image from the app next."));

    m_view.set_buffer(m_buffer);
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
    append(*scroller);
}

void ReviewPage::refresh()
{
    m_buffer->set_text(summary(m_window));
}

Gtk::Widget *ReviewPage::primaryInput() const
{
    return const_cast<Gtk::TextView *>(&m_view);
}

} // namespace kineticos
