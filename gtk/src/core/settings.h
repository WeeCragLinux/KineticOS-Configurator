#pragma once

#include <glibmm/keyfile.h>

#include <string>

namespace kineticos {

// User preferences on a GKeyFile stored in $XDG_CONFIG_HOME/kinetic-configurator/settings.ini.
// Every setter saves immediately; a failure to persist is never fatal.
class Settings final {
public:
    Settings();
    explicit Settings(std::string path);

    // Whether the compositor draws the title bar (server-side decorations) and the header
    // bar sits inside the window instead.
    bool systemTitleBar() const;
    void setSystemTitleBar(bool enabled);

    // The image project the user last opened, or empty.
    std::string checkoutPath() const;
    void setCheckoutPath(const std::string &path);

    const std::string &path() const { return m_path; }

private:
    void save();

    std::string m_path;
    Glib::RefPtr<Glib::KeyFile> m_file;
};

} // namespace kineticos
