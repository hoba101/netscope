#!/usr/bin/env bash
set -euo pipefail
# Build NetScope RPM on Fedora/RHEL-like systems
# Copyright (c) 2026 miro (hoba101), GPL-3.0-or-later
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
VER="$(cd "$ROOT" && python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
NAME="netscope"
TARBALL="${NAME}-${VER}.tar.gz"
TOP="${TMPDIR:-/tmp}/netscope-rpm-build-$$"
RPMTOP="${RPMTOP:-$HOME/rpmbuild}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; MISSING=1; }; }
MISSING=0
need_cmd python3
need_cmd tar
if ! command -v rpmbuild >/dev/null 2>&1; then echo "rpmbuild not found. On Fedora: sudo dnf install -y rpm-build rpmdevtools python3-devel desktop-file-utils"; exit 1; fi
if [[ "${MISSING:-0}" == "1" ]]; then exit 1; fi
if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "rpmbuild not found. On Fedora run:"
  echo "  sudo dnf install -y rpm-build rpmdevtools python3-devel desktop-file-utils"
  echo "Then re-run: bash packaging/rpm/build-rpm.sh"
  exit 1
fi

mkdir -p "$RPMTOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
rm -rf "$TOP"; mkdir -p "$TOP/$NAME-$VER"
tar -C "$ROOT" --exclude='.git' --exclude='.venv' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='__pycache__' --exclude='*.pyc' --exclude='dist' --exclude='build' --exclude='*.bak' --exclude='.flatpak-builder' --exclude='flatpak-build' -cf - . | tar -C "$TOP/$NAME-$VER" -xf -
tar -C "$TOP" -czf "$RPMTOP/SOURCES/$TARBALL" "$NAME-$VER"
cp "$ROOT/packaging/rpm/netscope.spec" "$RPMTOP/SPECS/"
# keep Version in spec aligned (simple check)
sed -i "s/^Version:.*/Version:        $VER/" "$RPMTOP/SPECS/netscope.spec"
echo "Building RPM for $NAME $VER ..."
rpmbuild -ba "$RPMTOP/SPECS/netscope.spec"
echo
echo "Done. Packages:"
find "$RPMTOP/RPMS" "$RPMTOP/SRPMS" -name "${NAME}*${VER}*" -type f 2>/dev/null | sort
