Name:           kinetic-configurator
Version:        0.4.0
Release:        7%{?dist}
Summary:        KineticOS Image Configurator

License:        MIT
URL:            https://github.com/WeeCragLinux/KineticOS-Configurator
# Generated from the checked-out commit by `make source` or `make srpm`.
Source0:        %{name}-%{version}.tar.gz

# The root CMakeLists.txt builds the GTK 4 application in gtk/; the earlier Python
# configurator in source/ is not built.
%global app_id com.weecraglinux.kinetic-configurator

BuildRequires:  cmake >= 3.20
BuildRequires:  cmake-rpm-macros
BuildRequires:  gcc-c++
BuildRequires:  ninja-build
BuildRequires:  pkgconfig(gtkmm-4.0) >= 4.20
BuildRequires:  pkgconfig(libadwaita-1) >= 1.6
BuildRequires:  glib2-devel
BuildRequires:  desktop-file-utils
BuildRequires:  appstream

Requires:       git
Requires:       dcli-bootc
Requires:       polkit

Provides:       kineticos-image-builder = %{version}-%{release}
Obsoletes:      kineticos-image-builder < 0.2.0
Provides:       KineticOS-Configurator = %{version}-%{release}
Obsoletes:      KineticOS-Configurator < 0.4.0

%description
KineticOS Configurator clones, opens, configures, updates, resets, and builds a
Kineticos image project. A guided wizard walks through the base image,
per-module app selection, optional repositories and removals, then writes
profile.yaml and modules/*.yaml and runs dcli-bootc gen. After generation it
can run dcli-bootc build and, with confirmation, switch to the new image and
reboot. Reset creates a full backup before restoring the selected project to
the latest upstream template.

%prep
%autosetup -n %{name}-%{version}

%build
%cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
%cmake_build

%install
%cmake_install

%check
%ctest
desktop-file-validate %{buildroot}%{_datadir}/applications/%{app_id}.desktop
appstreamcli validate --no-net %{buildroot}%{_datadir}/metainfo/%{app_id}.metainfo.xml

%files
%license LICENSE
%doc README.md CHANGELOG.md HELP.md
%{_bindir}/%{name}
%{_libexecdir}/kinetic-configurator/kinetic-configurator-helper
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/metainfo/%{app_id}.metainfo.xml
%{_datadir}/polkit-1/actions/%{app_id}.run-helper.policy
%{_datadir}/icons/hicolor/48x48/apps/%{name}.png
%{_datadir}/icons/hicolor/64x64/apps/%{name}.png
%{_datadir}/icons/hicolor/128x128/apps/%{name}.png
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png

%changelog
* Wed Oct 14 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-7
- Fix duplicate "Build image now?" dialogs: the async task reconnected its
  dispatcher on every run, so re-running the wizard after going back ran the
  completion (and its dialog) once per accumulated connection. The dispatcher
  is now connected once, and a second write/generate is ignored while one is in
  flight
* Wed Oct 14 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-6
- When the freshly built image is identical to the deployment the computer is
  currently booted from, state that it is the same image and offer to exit or go
  back and change the selections, instead of offering the switch and reporting a
  switch that changed nothing
* Wed Oct 14 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-5
- Show the Yes/No controls for any, not just the Flatpak, yes/no question a
  build command asks (for example dcli-bootc's "Pull the latest base and
  rebuild fresh … instead? [y/N]"), and label the row generically
* Tue Oct 13 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-4
- Regenerate the app icon with a transparent background
* Tue Oct 13 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-3
- Run build and switch through a privileged helper and a polkit action, so the
  system polkit agent (Noctalia) shows the branded authentication dialog
- Move the Back button next to Next on the right of the header bar
* Tue Oct 13 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-2
- Attach the project chooser window to the application so it stays open when
  launched without a project (terminal and app launcher)
* Tue Oct 13 2026 WeeCragLinux <weecraglinux@users.noreply.github.com> - 0.4.0-1
- Rewrite the application in GTK 4 (gtkmm) and libadwaita, following the GTK
  Desktop Application Standard and the LGL reference applications
- Standard window shell: header bar, both title bar modes, main menu, Alt-tap,
  notices, About dialog and a help window
- Follow the desktop theme live through a ThemeWatcher
- Store preferences in ~/.config/kinetic-configurator/settings.ini
- Keep the earlier Python configurator in source/ for reference only
* Tue Oct 13 2026 KineticOS Configurator contributors - 0.3.0-1
- Restyle the Python configurator to the standard (window shell, theming, settings.ini)
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-8
- Add Yes/No controls for the user Flatpak build prompt and remove the obsolete image warning
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-7
- Make package removals opt-in and selectable in the configurator
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-6
- Warn users that the image has no file manager or screenshot tool
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-5
- Keep base packages mandatory and out of app-selection pages
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-4
- Make all app modules selectable and preserve profile formatting
- Couple browser vendor repositories to app choices and add the experimental Deck image
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-3
- Replace corrupt checkouts with validated fresh clones for update and reset
- Reapply saved base-image, module, and app choices after full updates
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-2
- Add a backed-up reset-to-upstream action and add/remove-only template sync
- Rename the RPM to KineticOS-Configurator and document KineticOS install commands
* Tue Oct 13 2026 Kineticos Image Builder contributors - 0.2.0-1
- Package the configurator, project chooser, and in-app build actions
