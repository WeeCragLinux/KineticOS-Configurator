#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_ROOT="${1:-${SCRIPT_DIR}/..}"
SOURCE_ROOT="$(cd -- "${SOURCE_ROOT}" && pwd)"
BUILD_ROOT="${RPM_BUILD_ROOT:-${HOME}/rpmbuild}"
OUTPUT_DIR="${RPM_OUTPUT_DIR:-${PACKAGE_ROOT}}"
NAME="KineticOS-Configurator"
VERSION="0.2.0"
RELEASE="4"
SOURCE_DIR="${BUILD_ROOT}/SOURCES"
SOURCE_TARBALL="${SOURCE_DIR}/${NAME}-${VERSION}.tar.gz"

if [[ ! -d "${SOURCE_ROOT}/configurator" ]]; then
    echo "Configurator source directory is incomplete: ${SOURCE_ROOT}" >&2
    exit 2
fi
if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "rpmbuild is required (install rpm-build on KineticOS)." >&2
    exit 127
fi

mkdir -p "${BUILD_ROOT}"/{BUILD,BUILDROOT,RPMS,SOURCES,SRPMS} "${OUTPUT_DIR}"
tar -czf "${SOURCE_TARBALL}" \
    --transform="s,^,${NAME}-${VERSION}/," \
    -C "${PACKAGE_ROOT}" README.md LICENSE \
    -C "${SOURCE_ROOT}" \
    kinetic-configurator \
    configurator/__init__.py configurator/app.py configurator/project.py \
    configurator/template_sync.py configurator/workspace.py \
    tests/test_app.py tests/test_project.py tests/test_template_sync.py tests/test_workspace.py \
    -C "${SOURCE_ROOT}/packaging/assets" \
    kineticos-image-builder.desktop kineticos-image-builder.svg

rpmbuild -ba \
    --define "_topdir ${BUILD_ROOT}" \
    "${SOURCE_ROOT}/packaging/KineticOS-Configurator.spec"

cp "${BUILD_ROOT}/RPMS/noarch/${NAME}-${VERSION}-${RELEASE}"*.rpm "${OUTPUT_DIR}/"
cp "${BUILD_ROOT}/SRPMS/${NAME}-${VERSION}-${RELEASE}"*.src.rpm "${OUTPUT_DIR}/"
printf 'RPMs copied to %s\n' "${OUTPUT_DIR}"
