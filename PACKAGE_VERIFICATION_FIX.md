# Package verification fix request

## Problem

The configurator's image verifier can report a package as “should have been
removed” even when the same package is selected in a later, enabled app module.
For example, a package may be listed under `remove:` in
`modules/removals.yaml` and also under `packages:` in an app module. The
generated build removes base-image packages first, then installs selected app
packages afterward. The later selection is therefore the intended final state.

## Required behavior

Derive expected package state from the modules actually enabled and composed by
the build, using the same order as the generated build script:

- A selected package installed by a later module is expected in the final image,
  even if an earlier module removes it.
- A package listed for removal is expected absent only when no later enabled
  module selects it for installation.
- A selected package that is absent from the image must still be reported as
  missing.
- A removal-only package that remains in the image must still be reported as
  “should have been removed.”
- Handle remove/install overlaps generically; do not special-case package names.

When removals run before app modules, the effective removal set is:

```text
effective_removals = removed_packages - selected_install_packages
```

Check `effective_removals` for packages that remain in the image, and check all
selected install packages for packages missing from the image. Only include
packages from modules that are actually enabled and composed. A commented-out
or disabled module must not make a package expected.

## Regression tests

1. A package in `remove:` and selected by a later enabled module is not reported
   as “should have been removed” when present in the image.
2. The same selected package is still reported as missing when absent from the
   image.
3. A package in `remove:` with no later enabled selection is reported if it
   remains in the image.
4. A package selected only in a disabled module is not treated as an install.
5. A selected package such as Thunar that is genuinely absent remains a
   “missing from image” error; do not suppress it as part of the overlap fix.

This request concerns package-presence validation only. Missing desktop
launcher entries for installed packages are a separate issue and should not be
inferred from these package checks.
