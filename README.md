# KineticOS Configurator

RPM downloads for the KineticOS Image Configurator. This repository contains
the installable binary RPM and its source RPM; it does not contain the OS image
project or built image.

## Latest release: 0.2.0-1.fc44

- [KineticOS Configurator RPM](KineticOS-configurator-0.2.0-1.fc44.noarch.rpm)
- [Source RPM](KineticOS-Configurator-0.2.0-1.fc44.src.rpm)

The binary is a `noarch` RPM built on Fedora 44. It declares dependencies on
Python 3, PySide6, Git, and `dcli-bootc`.

## Install

On an rpm-ostree-based Kineticos system, download the binary RPM and run:

```bash
sudo rpm-ostree install ./KineticOS-configurator-0.2.0-1.fc44.noarch.rpm
systemctl reboot
```

The app is also available from the desktop app menu as **KineticOS Image
Configurator**, or from a terminal as `kinetic-configurator`.

On first launch, choose where to clone the image project. The app then lets you
configure the project, generate its build files, and optionally run the image
build. After a successful build, it asks before switching to the new image and
rebooting.

## Rebuild from source

The source RPM contains the Python app, tests, desktop entry, icon, and RPM
specification. On a Fedora build host with the required build dependencies:

```bash
rpmbuild --rebuild KineticOS-Configurator-0.2.0-1.fc44.src.rpm
```

The image project itself is cloned by the app into the user's chosen writable
directory; it is not bundled in either RPM.
