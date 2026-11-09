#!/usr/bin/env bash
set -euo pipefail
# NetScope installer — Copyright (c) 2026 miro (hoba101), GPL-3.0-or-later
PREFIX="${PREFIX:-}"
MODE="${1:-user}"
if [[ "$MODE" == "system" ]]; then
  PREFIX="${PREFIX:-/usr/local}"
  SUDO="${SUDO:-sudo}"
else
  PREFIX="${PREFIX:-$HOME/.local}"
  SUDO=""
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Installing NetScope to $PREFIX"
$SUDO mkdir -p "$PREFIX/lib/netscope" "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps" "$PREFIX/share/metainfo"
# Replace the previous copy completely so removed modules do not linger.
$SUDO rm -rf "$PREFIX/lib/netscope/netscope"
$SUDO mkdir -p "$PREFIX/lib/netscope"
$SUDO cp -a "$ROOT/netscope" "$PREFIX/lib/netscope/"
$SUDO install -Dm755 /dev/stdin "$PREFIX/bin/netscope" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$PREFIX/lib/netscope\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/python3 -m netscope "\$@"
EOF
$SUDO cp "$ROOT/netscope.desktop" "$PREFIX/share/applications/io.github.hoba101.NetScope.desktop"
$SUDO sed -i "s|^Exec=.*|Exec=$PREFIX/bin/netscope|" "$PREFIX/share/applications/io.github.hoba101.NetScope.desktop" || true
$SUDO cp "$ROOT/assets/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg" "$PREFIX/share/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg"
$SUDO cp "$ROOT/io.github.hoba101.NetScope.metainfo.xml" "$PREFIX/share/metainfo/io.github.hoba101.NetScope.metainfo.xml"
update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
echo "Done. Run: netscope"