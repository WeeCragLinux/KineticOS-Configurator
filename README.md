# KineticOS Configurator

**Latest RPM version:**
[`0.4.0-7.fc44`](https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.4.0-7)
(`kinetic-configurator`).

KineticOS Configurator is a **GTK 4 (gtkmm) + libadwaita** desktop app that
clones, configures, updates, resets, and builds a KineticOS bootc image project.
A guided wizard edits `profile.yaml` and `modules/*.yaml`, runs `dcli-bootc gen`,
and can build and switch the image for you.

The GTK source is in `gtk/`, the RPM packaging is in `packaging/`, and the built
RPMs are at this repository root. The earlier Python/PySide6 configurator is kept
in `source/` for reference only — it is not built or packaged.

Requires `git` and [`dcli-bootc`](https://copr.fedorainfracloud.org/coprs/theblackdon/dcli-bootc)
(plus `polkit`, which is used for the privileged build/switch steps).

## Install the RPM

These RPMs are for machines running **KineticOS**. Download the binary RPM from the
[latest GitHub release](https://github.com/WeeCragLinux/KineticOS-Configurator/releases/latest),
then install it with DNF:

```bash
sudo dnf install ./kinetic-configurator-0.4.0-7.fc44.x86_64.rpm
```

For the persistent KineticOS usr-overlay, use either equivalent command:

```bash
sudo kinpkg install ./kinetic-configurator-0.4.0-7.fc44.x86_64.rpm
sudo ki install ./kinetic-configurator-0.4.0-7.fc44.x86_64.rpm
```

Do not install this package with `rpm-ostree`.

Launch it from your app menu, or from a terminal:

```bash
kinetic-configurator
# or open a project directly, skipping the chooser:
kinetic-configurator --project /path/to/kinetic-image-builder
```

## Using the configurator

### 1. Choose a project

On first launch the configurator asks where to put the image project, then
remembers it. On later launches it offers:

- **Open saved project** — reopen the folder you used last.
- **Update full template, keep my choices** — replaces the project with a fresh
  upstream clone and reapplies your base-image, module, app, and list-item
  choices wherever matching entries remain. New entries use upstream defaults and
  removed entries disappear; other manual edits are replaced. A complete backup of
  the previous folder is kept beside it.
- **Reset project to a fresh template** — replaces the project with a fresh
  upstream clone and discards all choices (also with a sibling backup).
- **Clone image project…** / **Open an existing project…** — start from a new
  clone, or point at an existing folder containing `profile.yaml` and `modules/`.

### 2. Configure with the wizard

- **Base image** — `kineticos:default` (AMD and Intel), `:nvidia` (Turing or
  newer NVIDIA), `:nvidia-legacy` (older NVIDIA), or `:deck` (marked **very
  early** and **not recommended for normal use**). The current image stays
  selected by default.
- **Per-module app selection** — every module with selectable apps gets its own
  page. The baseline `base`, `rpmfusion`, modules stay enabled; the
  base package list is mandatory and is not offered as app choices. An app module
  is enabled only when at least one of its choices is selected. Newly discovered
  modules are added to `profile.yaml` disabled automatically — there is no
  module-selection prompt.
- **Optional repositories and removals** — the `removals` module starts disabled
  and each removal is opt-in; selected removals can be turned off here. If no
  selected app needs a repository, the page offers to disable RPM Fusion,
  or an already-enabled Brave/Vivaldi vendor repo. Leaving a vendor-repo option
  unchecked preserves its current state. Selecting Brave or Vivaldi enables the
  matching vendor repo command in the browser module's `pre` script before DNF
  installs the package.
- **Review** — a summary of the base image and every module with its selected
  apps and removals.

The wizard writes `profile.yaml` and `modules/*.yaml`, then runs `dcli-bootc gen`.

### 3. Build and switch

After generation the app offers to run `dcli-bootc build` (build only, no
switch). The build console streams the full output live. If the build asks
whether to apply changes to the current user's Flatpak installation, choose
**Yes** or **No** in the build window — the app does not apply those changes for
you. When the build succeeds the app separately asks whether to switch to the
new image and reboot. If the image you built is identical to the deployment this
computer is currently running, the app says so instead of offering the switch,
and asks whether to exit or go back to the first step and change your selections.

### Privileges

The GUI always runs as your normal user and never as root. The two privileged
steps — **build** and **switch** — run through a small, allow-listed helper:

- Helper: `/usr/libexec/kinetic-configurator/kinetic-configurator-helper`
  (only supports `build` and `switch`, validates the project path, and execs
  `dcli-bootc` directly — never through a shell).
- Polkit action: `com.weecraglinux.kinetic-configurator.run-helper`.

The GUI invokes the helper with `pkexec`, so your **system polkit agent**
(Noctalia) shows the authentication dialog:
*“KineticOS Configurator needs administrator privileges to build and switch your
image.”*

### Preferences

Preferences live in `~/.config/kinetic-configurator/settings.ini`:

| Group | Key | Meaning |
|---|---|---|
| `window` | `systemTitleBar` | Whether the compositor draws the title bar |
| `project` | `checkoutPath` | The image project opened last |

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+Q | Quit |
| Ctrl+Shift+M | Toggle the system title bar |
| Alt (tap) | Open or close the main menu |
| F10 | Open the main menu |
| F1 | Help |

The app follows the desktop theme live (dark mode, accent colour, and the
monospace font), including changes made by theme generators such as Noctalia.

## Building from source

The GTK 4 application builds from the repository root with CMake:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build --output-on-failure
```

Run it with `./build/kinetic-configurator`, or install system-wide with
`cmake --install build`. Build requirements: `cmake`, a C++17 compiler,
`gtkmm-4.0` (>= 4.20), `libadwaita-1` (>= 1.6) and `glib2-devel`.

### Build the RPMs

With `rpm-build` installed:

```bash
make          # source archive: kinetic-configurator-0.4.0.tar.gz
make srpm     # source RPM into result/
```

Version and release are read from `packaging/kinetic-configurator.spec`; on a
release, update the spec together with the metainfo `<releases>` list,
`CHANGELOG.md`, and this README's latest-version line.

## Standard compliance

This project follows the internal **GTK Desktop Application Standard** and the
LGL reference applications (`lgl-papercutter`, `lgl-emoji-picker`): GTK 4 (gtkmm)
with libadwaita, the shared header bar and main menu, both title bar modes, live
desktop theming through a `ThemeWatcher`, a help window and About dialog, and
preferences in `settings.ini`. The `build`/`switch` helper follows the
**Privileged Operations Standard**: the GUI is unprivileged, privileged work is
isolated in an allow-listed helper, there is no shell execution, and inputs are
validated. Core logic is widget-free and unit tested with the GLib test framework.

---

## The image project the configurator manages

The sections below describe the KineticOS bootc image itself (the `profile.yaml`
and `modules/` the configurator edits). A modular image based on
`ghcr.io/theblack-don/kineticos:default` by default: a small always-on core, with
everything else opt-in. `build_files/build.sh` is generated — edit
`modules/*.yaml`, then run `dcli-bootc gen`.

To build manually instead of through the app:

```bash
dcli-bootc gen
dcli-bootc build --no-switch
```

Then rebase/switch to the built image with `bootc` (follow your current system's
rebase procedure; keep a known-good deployment pinned so you can roll back).

### Modules

Toggle in `profile.yaml` under `enabled_modules:` (comment a line out to
disable that whole module). Order matters: `base` first, `rpmfusion`
before anything needing it.

| Module | Contents | Needs `rpmfusion`? |
|---|---|---|
| `base` | update timer. Always on. | no |
| `rpmfusion` | RPMFusion free + nonfree repos. Leave on unless minimal. | — (it *is* the repos) |
| `browsers` | helium, chromium, firefox, brave-browser, brave-origin, vivaldi | brave/vivaldi need their own repo setup (in-module) |
| `content` | obs-studio, audacity, kdenlive, gimp, pavucontrol, easyeffects, vlc, mpv, Spotify flatpak | yes (vlc, mpv) |
| `gaming` | prismlauncher, mangohud, goverlay; steam, lutris commented out | yes (if steam uncommented) |
| `comms` | telegram, thunderbird, discord (commented) | yes (if discord uncommented) |
| `terminals` | kitty, konsole | no |
| `dev` | Zed Flatpak (commented out) | no |
| `lgl-tools` | LGL System Loadout, Colour Picker, DNF Helper, Emoji Picker, Keychron Helper, Papercutter, Scheduler Manager | no (Scheduler Manager also needs `scx-tools` and `scx-scheds` from `bieszczaders/kernel-cachyos-addons`) |

LGL System Loadout's kernel-changing feature does not work with this bootc-based
image. Do not use it to switch kernels.

### Kineticos usr-overlay (kinpkg)

Kineticos provides the **usr-overlay** as a package-management layer alongside
the base image; it is a Kineticos feature, not a separate image variant. The
overlay is managed by `kinpkg`, which tracks overlay packages separately from
the base image's packages. During builds and updates, `kinpkg` reconciles the
overlay package set: packages added to the set are installed, and removed
packages are uninstalled. This lets overlay-managed customizations persist
across base-image updates while avoiding file conflicts with packages in the
base image.

### Enable / disable apps

Choose apps with the GUI configurator, or edit the module files manually. In each
`modules/*.yaml`, lines starting with `# -` are disabled; uncomment a package line
to install it, or comment it out to remove it:

```yaml
packages:
 - mpv
 # - vlc
```

Some apps need their repo lines toggled alongside the package (brave,
vivaldi) — the comments in each file say which lines belong together.
After any change, re-run `dcli-bootc gen` before building.

### Base image variants

The default is `ghcr.io/theblack-don/kineticos:default` for AMD and Intel GPUs.
Select the variant that matches your GPU in the wizard: `:default` for AMD and
Intel, `:nvidia` for Turing and newer Nvidia GPUs, or `:nvidia-legacy` for older
Nvidia GPUs. The `:deck` image is very early and not recommended for normal use.
The configurator saves your selection to `profile.yaml` → `base_image:`. You can
also change it manually:

```yaml
base_image: ghcr.io/theblack-don/kineticos:default
```

`profile.yaml` also has an `nvidia_base_image:` key (currently `null`).
Its exact semantics depend on your dcli-bootc version — check
`dcli-bootc gen --help` on your build host before relying on it; the
one-line `base_image:` edit above always works regardless.

### Extras

- **fastfetch config (opt-in):** `files/fastfetch-config.jsonc` is *not*
  baked into the image. After booting, run from a repo checkout:
  ```bash
  bash scripts/apply-fastfetch-config.sh        # your ~/.config only
  bash scripts/apply-fastfetch-config.sh --system  # also /etc default (needs sudo)
  ```
  The script also offers bash auto-run in new terminals.
- **Flatpaks:** listed under `flatpaks:` per module (see Spotify in `content`).

## License

This project is licensed under the [MIT License](LICENSE). It covers this
repository's original content; Kineticos, dcli-bootc, and third-party packages
and repositories remain under their own terms.
