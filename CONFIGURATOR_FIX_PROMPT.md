# Configurator fix request

Please update the **separately distributed Kineticos configurator** to match
the requirements below. The image repository contains the module/profile YAML,
but the configurator UI is a separate RPM and must be updated and rebuilt
separately. In this repository, the older Python source is available in Git
history before commit `6db86a7`; the current branch removed the configurator
source and launcher.

## Required behavior

1. **Do not ask users to enable modules before choosing apps.** Make every
   module's app page available in the wizard. App modules must be enabled in
   `profile.yaml` only when the user selects at least one app from that module's
   page. If a module is newly discovered, add it as disabled automatically
   rather than opening a “New modules found / Select modules to add” prompt.
2. **Keep the baseline modules enabled by default:** `base`, `rpmfusion`, and
   `terra`. Keep RPMFusion and Terra enabled unless the user chooses to disable
   them at the end and no selected app requires them. Do not offer to disable
   either repository when a selected app needs it.
3. **Manage browser vendor repos with the selected apps.** Selecting
   `brave-browser` or `brave-origin` must enable their shared Brave repo;
   selecting `vivaldi-stable` must enable the Vivaldi repo. Enable the repo in
   the browser module's `pre` script, before DNF installs that app.
4. **Offer to disable unused, already-enabled browser repos on the existing
   final optional-repositories screen.** If neither Brave app is selected but
   the shared Brave repo command is active, offer a checkbox to disable it. If
   Vivaldi is not selected but its repo command is active, offer the equivalent
   checkbox. Hide each option when its repo is already disabled. Never offer to
   disable a repo required by a selected app. Keep all these choices together
   with the RPMFusion/Terra disable options on that same screen.
5. **Add the Deck image to the base-image picker:**
   `ghcr.io/theblack-don/kineticos:deck`. Clearly label it “very early” and
   “not recommended for normal use.” Keep the current default image as the
   default selection.

## Profile parsing and persistence

The current configurator parser is sensitive to the formatting of
`enabled_modules:` entries. Make it robust to disabled module entries and
comments so a profile with all known modules listed does not trigger a module
selection prompt. Preserve unrelated profile comments and formatting when
saving. The image repo keeps the baseline entries active and app-module entries
commented out; the configurator should write the active state based on the
user's selections and optional-repository choices.

## Acceptance checks

- With no apps selected, no module-discovery dialog appears. The profile keeps
  `base`, `rpmfusion`, and `terra` enabled; all app modules remain disabled.
- Selecting one app enables only its app module. Selecting apps that need
  RPMFusion or Terra keeps the required repo enabled and hides its disable
  option.
- Selecting either Brave package enables the shared Brave repo command before
  the package install; selecting Vivaldi enables the Vivaldi repo command
  before its package install.
- With no matching app selected and a vendor repo command already enabled, the
  final optional-repositories screen offers to disable that repo. Choosing the
  option comments out the command; leaving it unchecked preserves it.
- The Deck image appears in the picker with the warning, while the current
  default image remains selected by default.
- Add or update tests for module discovery, profile round-tripping, repo/app
  coupling, optional-screen visibility, and base-image choices. Rebuild the
  configurator RPM and report where the updated artifact is published.
