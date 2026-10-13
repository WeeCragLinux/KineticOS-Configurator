#pragma once

#include "core/project.h"

#include <gtkmm/box.h>
#include <gtkmm/checkbutton.h>
#include <gtkmm/textview.h>

#include <string>
#include <utility>
#include <vector>

namespace kineticos {

class Window;

// Wizard pages shown inside the main window. Each page is a plain box that reads and writes
// the shared Selection on the window; the window owns the flow.
class BasePage final : public Gtk::Box {
public:
    explicit BasePage(Window &window);

    Gtk::Widget *primaryInput() const;

private:
    Window &m_window;
    Gtk::CheckButton *m_first{nullptr};
};

class ModulePage final : public Gtk::Box {
public:
    ModulePage(Window &window, const Module &module);

    const std::string &moduleName() const { return m_name; }
    bool isRemovalPage() const { return m_removal; }
    Gtk::Widget *primaryInput() const;

private:
    void sync();

    Window &m_window;
    std::string m_name;
    bool m_removal{false};
    std::vector<std::pair<App, Gtk::CheckButton *>> m_boxes;
};

class OptionalPage final : public Gtk::Box {
public:
    explicit OptionalPage(Window &window);

    void refresh();
    Gtk::Widget *primaryInput() const;

private:
    Window &m_window;
    Gtk::CheckButton *m_rpm{nullptr};
    Gtk::CheckButton *m_terra{nullptr};
    Gtk::CheckButton *m_removals{nullptr};
    Gtk::CheckButton *m_brave{nullptr};
    Gtk::CheckButton *m_vivaldi{nullptr};
};

class ReviewPage final : public Gtk::Box {
public:
    explicit ReviewPage(Window &window);

    void refresh();
    Gtk::Widget *primaryInput() const;

private:
    Window &m_window;
    Gtk::TextView m_view;
    Glib::RefPtr<Gtk::TextBuffer> m_buffer;
};

// A checkbox label for an app, naming its section.
std::string appLabel(const App &app);

} // namespace kineticos
