# KineticOS Configurator

**Latest RPM version:** `0.2.0-5.fc44` (`KineticOS-Configurator`).

The packaged configurator source is in `source/`; the RPM files are at this repository root.

A modular bootc image based on `ghcr.io/theblack-don/kineticos:default` by default.
Small always-on core, everything else opt-in: enable the modules you want,
comment out the apps you don't.

Built with [dcli-bootc](https://copr.fedorainfracloud.org/coprs/theblackdon/dcli-bootc).
`build_files/build.sh` is generated — edit `modules/*.yaml`, then run
`dcli-bootc gen`.

## Configure and build (GUI)

Run the configurator:

```bash
./source/kinetic-configurator
```

On first launch, choose where to clone the image project. The configurator
remembers that project location, lets you open an existing project, and can update
it from a fresh upstream clone. Update reapplies the current base-image, module, app,
and list-item choices wherever matching entries remain. New entries use upstream
defaults and removed entries disappear. Other manual edits are replaced; a complete
backup of the previous project folder is kept beside it.
To open a project directly without the project chooser, run
`./source/kinetic-configurator --project /path/to/kinetic-image-builder`.

The saved-project chooser also has **Reset project to a fresh template**. After
confirmation, it replaces the selected folder with a fresh upstream clone without
reapplying choices. The previous folder is kept as a complete sibling backup.

The wizard asks for a base image (`kineticos:default` for AMD and Intel,
`:nvidia` for Turing and newer NVIDIA cards, `:nvidia-legacy` for older NVIDIA
cards). The `:deck` image is also listed as **very early** and **not recommended
for normal use**. The current image remains selected by default.

The wizard provides an app page for every module with selectable apps. Newly
discovered modules are added to `profile.yaml` disabled automatically; there is
no module-selection prompt. The baseline `base`, `rpmfusion`, and `terra`
modules stay enabled by default; the base package list is mandatory and is not
offered as app choices. An app module is enabled only when at least one of its
apps is selected. Selecting Brave or Vivaldi enables its vendor repo
command in the browser module's `pre` script before DNF installs the package.
At the end, if no selected app needs a repository, the configurator offers to
disable RPM Fusion, Terra, or an already-enabled Brave/Vivaldi repo. RPM Fusion
and Terra stay enabled unless explicitly disabled; leaving a vendor-repo option
unchecked preserves that repo's current state. The configurator writes `profile.yaml`
and `modules/*.yaml`, runs `dcli-bootc gen`, and offers to run
`dcli-bootc build`. The build does not switch deployments automatically; after
a successful build, the app separately asks whether to switch to the new image
and reboot.

Requires Python 3, PySide6, Git, and `dcli-bootc` (the latter is needed for
generation/build; Git is needed to clone or update projects).

## Install the KineticOS Configurator RPM

These RPMs are for systems running **KineticOS**. Install the built package with
DNF:

```bash
sudo dnf install ./KineticOS-Configurator-0.2.0-5.fc44.noarch.rpm
```

For the persistent KineticOS usr-overlay, use either equivalent command:

```bash
sudo kinpkg install ./KineticOS-Configurator-0.2.0-5.fc44.noarch.rpm
sudo ki install ./KineticOS-Configurator-0.2.0-5.fc44.noarch.rpm
```

Do not install this package with `rpm-ostree`.

## Build the RPMs

The configurator source, tests, and RPM spec are in `source/`. With `rpm-build` installed, run:

```bash
./source/packaging/build-rpm.sh
```

The binary and source RPMs are written to this repository's top level.

## Build

The app can run the build after generation. To build manually instead:

```bash
dcli-bootc gen
dcli-bootc build --no-switch
```

To use it on a machine, rebase/switch to the built image with `bootc`
(follow your current system's rebase procedure; keep a known-good
deployment pinned so you can roll back).

## Modules

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

## Kineticos usr-overlay (kinpkg)

Kineticos provides the **usr-overlay** as a package-management layer alongside
the base image; it is a Kineticos feature, not a separate image variant. The
overlay is managed by `kinpkg`, which tracks overlay packages separately from
the base image's packages. During builds and updates, `kinpkg` reconciles the
overlay package set: packages added to the set are installed, and removed
packages are uninstalled. This lets overlay-managed customizations persist
across base-image updates while avoiding file conflicts with packages in the
base image.

## Enable / disable apps

You can choose apps with the GUI configurator (`./source/kinetic-configurator`), or
edit the module files manually. In each `modules/*.yaml`, lines starting with
`# -` are disabled; uncomment a package line to install it, or comment it out
to remove it:

```yaml
packages:
 - mpv
 # - vlc
```

Some apps need their repo lines toggled alongside the package (brave,
vivaldi) — the comments in each file say which lines belong together.
After any change, re-run `dcli-bootc gen` before building.

## Base image variants

The default is `ghcr.io/theblack-don/kineticos:default` for AMD and Intel GPUs.
Run `./source/kinetic-configurator` to select the variant that matches your GPU:
`:default` for AMD and Intel, `:nvidia` for Turing and newer Nvidia GPUs, or
`:nvidia-legacy` for older Nvidia GPUs. The `:deck` image is very early and not
recommended for normal use. The configurator saves your selection to
`profile.yaml` → `base_image:`. You can also change it manually:

```yaml
base_image: ghcr.io/theblack-don/kineticos:default
```

`profile.yaml` also has an `nvidia_base_image:` key (currently `null`).
Its exact semantics depend on your dcli-bootc version — check
`dcli-bootc gen --help` on your build host before relying on it; the
one-line `base_image:` edit above always works regardless.

## Extras

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
