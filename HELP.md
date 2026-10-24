# KineticOS Configurator Help

KineticOS Configurator clones, opens, configures, updates, resets, and builds a
Kineticos image project. This guide walks through the wizard and lists the
keyboard shortcuts.

## Before you start

You need Git and `dcli-bootc`. Git is used to clone and update projects;
`dcli-bootc` generates and builds the image. Those are pulled in by the package,
so a normal install is ready to use.

## The wizard

### 1. Choose a project

On first launch, choose where to clone the image project. The configurator
remembers that location, lets you open an existing project, and can update it
from a fresh upstream clone.

- **Open an existing project** — pick a folder containing `profile.yaml` and a
  `modules/` directory.
- **Clone a new project** — choose an empty location for the upstream clone.
- **Update from upstream** — reapplies your current base-image, module, app, and
  list-item choices wherever matching entries remain. New entries use upstream
  defaults and removed entries disappear. Other manual edits are replaced; a
  complete backup of the previous project folder is kept beside it.
- **Reset project to a fresh template** — after confirmation, replaces the
  selected folder with a fresh upstream clone without reapplying choices. The
  previous folder is kept as a complete sibling backup.

To skip the chooser and open a project directly, run:

```bash
kinetic-configurator --project /path/to/kinetic-image-builder
```

### 2. Base image

Choose the Kineticos image that matches your GPU:

| Image | For |
|---|---|
| `kineticos:default` | AMD and Intel GPUs |
| `kineticos:nvidia` | NVIDIA Turing or newer (GTX 16, RTX 20/30/40/50) |
| `kineticos:nvidia-legacy` | NVIDIA older than the 10 series |
| `kineticos:deck` | Very early; not recommended for normal use |

The current image stays selected by default.

### 3. Per-module app selection

Every module with selectable apps gets its own page. Check the software you want
included in your image. Newly discovered modules are added automatically
(disabled); there is no module-selection prompt.

- The baseline `base` and `rpmfusion` modules stay enabled by default.
- The base package list is mandatory and is not offered as app choices.
- An app module is enabled only when at least one of its choices is selected.
- The `removals` module starts disabled; each removal is opt-in. If none are
  selected, the module stays disabled.
- Selecting Brave or Vivaldi enables its vendor repository command in the
  browser module before DNF installs the package.

### 4. Optional repositories and removals

Review optional repositories. If the saved project already enables removals,
this page also offers to turn those removals off; removals chosen in the wizard
are applied directly and are not offered here again. Repositories that no
selected app needs can be disabled here; RPM Fusion stays enabled unless you
explicitly disable it, and leaving a vendor-repo option unchecked preserves
that repository's current state.

### 5. Review

Review your choices before anything is written. The summary lists the base image
and every module with its selected apps and removals.

### 6. Write changes

Writing updates `profile.yaml` and `modules/*.yaml`, then runs `dcli-bootc gen`.

### 7. Build

After a successful generation, the configurator offers to run
`dcli-bootc build`. The build runs with administrator privileges, so the app
answers **No** to dcli-bootc's question about applying changes to the root
user's Flatpak installation. After a successful build the app installs the
selected Flatpaks for your own user with `dcli-bootc flatpak sync`. They are not
baked into the image and do not appear in `/var/lib/flatpak`. If that sync
fails, the image is still valid; run `dcli-bootc flatpak sync -p <project>`
later. The build does not switch deployments automatically. After a successful
build, the app separately asks whether to switch to the new image and reboot.

If the image you built is identical to the deployment this computer is currently
running, the app says so instead of offering the switch, and asks whether to
exit the configurator or go back to the first step and change your selections.
Nothing has changed on the system in that case, so there is nothing to reboot
into.

Building and switching are privileged steps. The app runs as your normal user
and asks your system polkit agent (for example, Noctalia) for administrator
authentication before it runs them.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+Q | Quit |
| Ctrl+Shift+M | Toggle system title bar |
| Alt (tap) | Open or close the main menu |
| F10 | Open the main menu |
| F1 | Help |
| Escape | Close a menu or dialog |

## Files the configurator writes

- `profile.yaml` — base image and enabled modules.
- `modules/*.yaml` — per-module packages, scripts, and removals.
- Generated build files under the project (for example `build_files/build.sh`).

Your preferences (such as the system title bar mode) are stored in
`~/.config/kinetic-configurator/settings.ini`.

## Troubleshooting

- **`dcli-bootc` not found** — install `dcli-bootc`; generation and building
  need it.
- **Clone or update fails** — Git is required, and the destination must be
  writable. Corrupt checkouts are replaced with validated fresh clones.
- **Build fails** — the build window shows the full command output. Check it,
  fix the selection or project, and try again from the wizard.
- **Flatpaks are missing after a reboot** — the post-build sync may have failed.
  Run `dcli-bootc flatpak sync -p /path/to/your/project` as your normal user.
  Running `dcli-bootc build` manually with `sudo` also sends Flatpaks to root's
  home, so run it as your normal user instead.
