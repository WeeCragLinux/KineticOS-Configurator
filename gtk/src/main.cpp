#include "core/workspace.h"
#include "ui/chooser.h"
#include "ui/themewatcher.h"
#include "ui/window.h"

#include <gtk/gtk.h>

#include <glibmm/main.h>
#include <glibmm/miscutils.h>
#include <gtkmm/application.h>
#include <gtkmm/window.h>

#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace {

// Smoke-test hook: with KINETIC_CONFIGURATOR_GTK_SNAPSHOT=<folder>, every visible window is
// rendered to <folder>/<window title>.png once the app has settled, and the application
// quits.
void saveSnapshot(GtkWidget *widget, const std::string &path)
{
    const int width = gtk_widget_get_width(widget);
    const int height = gtk_widget_get_height(widget);
    GdkPaintable *paintable = gtk_widget_paintable_new(widget);
    GtkSnapshot *snapshot = gtk_snapshot_new();
    gdk_paintable_snapshot(paintable, GDK_SNAPSHOT(snapshot), width, height);
    if (GskRenderNode *node = gtk_snapshot_free_to_node(snapshot)) {
        GskRenderer *renderer = gtk_native_get_renderer(GTK_NATIVE(widget));
        const graphene_rect_t bounds = GRAPHENE_RECT_INIT(
            0.0f, 0.0f, static_cast<float>(width), static_cast<float>(height));
        GdkTexture *texture = gsk_renderer_render_texture(renderer, node, &bounds);
        gdk_texture_save_to_png(texture, path.c_str());
        g_object_unref(texture);
        gsk_render_node_unref(node);
    }
    g_object_unref(paintable);
}

void scheduleSnapshot(const Glib::RefPtr<Gtk::Application> &application)
{
    const std::string folder = Glib::getenv("KINETIC_CONFIGURATOR_GTK_SNAPSHOT");
    if (folder.empty())
        return;
    Glib::signal_timeout().connect_once(
        [application, folder] {
            GListModel *toplevels = gtk_window_get_toplevels();
            for (guint i = 0; i < g_list_model_get_n_items(toplevels); ++i) {
                auto *window = static_cast<GtkWidget *>(g_list_model_get_item(toplevels, i));
                const char *title = gtk_window_get_title(GTK_WINDOW(window));
                std::string name = title && *title ? title : "window-" + std::to_string(i);
                for (char &c : name) {
                    if (!g_ascii_isalnum(c))
                        c = '-';
                }
                if (gtk_widget_get_visible(window) && gtk_widget_get_realized(window))
                    saveSnapshot(window, Glib::build_filename(folder, name + ".png"));
                g_object_unref(window);
            }
            application->quit();
        },
        3000);
}

} // namespace

int main(int argc, char *argv[])
{
    // Parse --project/-p and keep the rest for GTK.
    std::string project;
    std::vector<char *> arguments;
    for (int index = 0; index < argc; ++index) {
        if (index > 0
            && (std::strcmp(argv[index], "--project") == 0
                || std::strcmp(argv[index], "-p") == 0)
            && index + 1 < argc) {
            project = argv[++index];
            continue;
        }
        arguments.push_back(argv[index]);
    }
    int argumentCount = static_cast<int>(arguments.size());
    // A second launch presents the running window; snapshot runs must stay separate.
    auto flags = Gio::Application::Flags::DEFAULT_FLAGS;
    if (!Glib::getenv("KINETIC_CONFIGURATOR_GTK_SNAPSHOT").empty())
        flags |= Gio::Application::Flags::NON_UNIQUE;
    auto application =
        Gtk::Application::create("com.weecraglinux.kinetic-configurator", flags);

    kineticos::Settings settings;
    std::unique_ptr<kineticos::Window> window;
    std::unique_ptr<kineticos::ChooserWindow> chooser;

    application->signal_startup().connect([&] {
        Glib::set_application_name("KineticOS Configurator");
        // Installed builds also get the icon from the desktop file's Icon= entry.
        Gtk::Window::set_default_icon_name("kinetic-configurator");
        kineticos::installApplicationStylesheet();
        application->add_action("quit", [&] {
            if (window)
                window->set_visible(false);
            if (chooser)
                chooser->set_visible(false);
            application->quit();
        });
        application->set_accel_for_action("app.quit", "<Control>q");
    });

    application->signal_activate().connect([&] {
        if (!project.empty() && kineticos::isProject(project)) {
            if (!window)
                window = std::make_unique<kineticos::Window>(application, project, settings);
            window->present();
        } else if (window) {
            window->present();
        } else if (!chooser) {
            chooser = std::make_unique<kineticos::ChooserWindow>(application, settings);
            chooser->signalChosen().connect([&](std::string path) {
                window = std::make_unique<kineticos::Window>(application, path, settings);
                if (chooser)
                    chooser->close();
                window->present();
            });
            chooser->present();
        }
        scheduleSnapshot(application);
    });

    char **argvPointer = arguments.data();
    const int status = application->run(argumentCount, argvPointer);
    window.reset();
    chooser.reset();
    return status;
}
