# Changelog

All notable changes to the KineticOS Configurator are recorded here. The
version numbering matches the RPM package version (`Version-Release`).

## [0.4.0-8] — 2026-10-20

- Remove Terra completely. The image no longer ships the Terra module, so the
  configurator no longer treats it as a baseline module or offers **Disable
  Terra**, and the `terra-mangohud` app coupling is gone. Saving a project now
  drops entries whose `modules/<name>.yaml` file no longer exists, so an old
  `- terra` line cannot keep a removed module enabled.
- Install Flatpaks for the real user. The build runs as root through polkit, so
  answering its **Apply these changes to your user flatpak installation?**
  prompt would have installed the apps under `/root`. The configurator now
  answers that prompt No, then runs `dcli-bootc flatpak sync` as your normal
  user after a successful build. A failed sync is a warning, not a build
  failure.

## [0.4.0-7] — 2026-10-14

- Fix duplicate **Build image now?** dialogs. The async task reconnected its
  dispatcher on every run, so going back and running the wizard again made the
  generation completion fire once per accumulated connection and spawn a stack
  of prompts. The dispatcher is connected once now, and a second write/generate
  is ignored while one is already in flight.

## [0.4.0-6] — 2026-10-14

- When the freshly built image is identical to the deployment the computer is
  currently booted from, stop offering the switch. The app now reads
  dcli-bootc's own identical-image report, states that the image is the same as
  the one already running, and asks whether to exit the configurator or go back
  to the first step and change the selections. Previously it opened a
  "Switching to the new image" console and reported a switch that changed
  nothing.

## [0.4.0-5] — 2026-10-14

- Show the **Yes**/**No** controls for any yes/no question a build command asks,
  not just the user Flatpak prompt. This covers dcli-bootc's "Pull the latest
  base and rebuild fresh (dcli-bootc update) instead? [y/N]" question, and the
  prompt row now uses a generic label instead of the Flatpak-specific wording.

## [0.4.0-4] — 2026-10-13

- Regenerate the application icon with a transparent background.

## [0.4.0-3] — 2026-10-13

- Run `build` and `switch` through a privileged helper and a custom polkit
  action, so the system polkit agent (Noctalia) shows the branded
  authentication dialog. The GUI stays unprivileged.
- Move the **Back** button next to **Next** on the right of the header bar.

## [0.4.0-2] — 2026-10-13

- Attach the project chooser window to the application so it stays open when
  launched without a project (terminal and app launcher).

## [0.4.0-1] — 2026-10-13

- Rewrite the application in GTK 4 (gtkmm) and libadwaita, following the GTK
  Desktop Application Standard and the LGL reference applications.
- Standard window shell: header bar with the logo and wordmark, both title bar
  modes, the main menu (Alt-tap and F10), notices, an About dialog and a help
  window (F1).
- Follow the desktop theme live through a `ThemeWatcher`.
- Store preferences in `~/.config/kinetic-configurator/settings.ini`.
- Keep the earlier Python configurator in `source/` for reference only.

## [0.3.0-1] — 2026-10-13

- Restyle the Python configurator to the standard: standard window shell,
  theming, and `settings.ini`.

## [0.2.0-8] — 2026-10-13

- Add Yes/No controls for the user Flatpak build prompt and remove the obsolete
  image warning.

## [0.2.0-7] — 2026-10-13

- Make package removals opt-in and selectable in the configurator.

## [0.2.0-6] — 2026-10-13

- Warn users that the image has no file manager or screenshot tool.

## [0.2.0-5] — 2026-10-13

- Keep base packages mandatory and out of app-selection pages.

## [0.2.0-4] — 2026-10-13

- Make all app modules selectable and preserve profile formatting.
- Couple browser vendor repositories to app choices and add the experimental
  Deck image.

## [0.2.0-3] — 2026-10-13

- Replace corrupt checkouts with validated fresh clones for update and reset.
- Reapply saved base-image, module, and app choices after full updates.

## [0.2.0-2] — 2026-10-13

- Add a backed-up reset-to-upstream action and add/remove-only template sync.
- Rename the RPM to KineticOS-Configurator and document KineticOS install
  commands.

## [0.2.0-1] — 2026-10-13

- Package the configurator, project chooser, and in-app build actions.

## [0.1.0-1] — 2026-10-13

- Initial RPM package of the KineticOS image builder.

[0.4.0-4]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.4.0-4
[0.4.0-3]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.4.0-3
[0.4.0-2]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.4.0-2
[0.4.0-1]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.4.0-1
[0.3.0-1]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.3.0-1
[0.2.0-8]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-8
[0.2.0-7]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-7
[0.2.0-6]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-6
[0.2.0-5]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-5
[0.2.0-4]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-4
[0.2.0-3]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-3
[0.2.0-2]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-2
[0.2.0-1]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.2.0-1
[0.1.0-1]: https://github.com/WeeCragLinux/KineticOS-Configurator/releases/tag/v0.1.0-1
