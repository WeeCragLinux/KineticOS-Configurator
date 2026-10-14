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

- The baseline `base`, `rpmfusion`, and `terra` modules stay enabled by default.
- The base package list is mandatory and is not offered as app choices.
- An app module is enabled only when at least one of its choices is selected.
- The `removals` module starts disabled; each removal is opt-in. If none are
  selected, the module stays disabled.
- Selecting Brave or Vivaldi enables its vendor repository command in the
  browser module before DNF installs the package.

### 4. Optional repositories and removals

Review optional repositories and selected removals. Repositories that no
selected app needs can be disabled here; RPM Fusion and Terra stay enabled
unless you explicitly disable them, and leaving a vendor-repo option unchecked
preserves that repository's current state.

### 5. Review

Review your choices before anything is written. The summary lists the base image
and every module with its selected apps and removals.

### 6. Write changes

Writing updates `profile.yaml` and `modules/*.yaml`, then runs `dcli-bootc gen`.

### 7. Build

After a successful generation, the configurator offers to run
`dcli-bootc build`. When the build asks whether to apply changes to the current
user's Flatpak installation, choose **Yes** or **No** in the build window; the
app does not apply those changes for you. The build does not switch deployments
automatically. After a successful build, the app separately asks whether to
switch to the new image and reboot.

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
