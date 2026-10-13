Name:           KineticOS-Configurator
Version:        0.2.0
Release:        7%{?dist}
Summary:        KineticOS Image Configurator
License:        MIT
URL:            https://github.com/WeeCragLinux/kinetic-image-builder
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  desktop-file-utils
BuildRequires:  git
BuildRequires:  python3
BuildRequires:  python3-pyside6
Requires:       git
Requires:       python3
Requires:       python3-pyside6
Requires:       dcli-bootc
Provides:       kineticos-image-builder = %{version}-%{release}
Obsoletes:      kineticos-image-builder < 0.2.0

%description
KineticOS Configurator clones, configures, updates, resets, and builds a
Kineticos image project. Reset creates a full backup before restoring the
selected project to the latest upstream template.

%prep
%autosetup -n %{name}-%{version}

%build

%install
install -Dpm 0755 kinetic-configurator \
    %{buildroot}%{_bindir}/kinetic-configurator
install -dpm 0755 %{buildroot}%{_datadir}/KineticOS-Configurator/configurator
install -pm 0644 configurator/*.py \
    %{buildroot}%{_datadir}/KineticOS-Configurator/configurator/
install -Dpm 0644 kineticos-image-builder.desktop \
    %{buildroot}%{_datadir}/applications/kineticos-image-builder.desktop
install -Dpm 0644 kineticos-image-builder.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/kineticos-image-builder.svg
install -Dpm 0644 README.md \
    %{buildroot}%{_docdir}/%{name}/README.md
install -Dpm 0644 LICENSE \
    %{buildroot}%{_docdir}/%{name}/LICENSE

%check
desktop-file-validate kineticos-image-builder.desktop
python3 -m unittest discover -s tests -v

%files
%{_bindir}/kinetic-configurator
%{_datadir}/KineticOS-Configurator/configurator/*.py
%{_datadir}/applications/kineticos-image-builder.desktop
%{_datadir}/icons/hicolor/scalable/apps/kineticos-image-builder.svg
%doc %{_docdir}/%{name}/README.md
%license %{_docdir}/%{name}/LICENSE

%changelog
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
