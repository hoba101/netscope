#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VER="$(python3 -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("'"$ROOT"'/pyproject.toml").read_text())["project"]["version"])')"
OUT="$ROOT/dist"
PKG="$OUT/netscope_${VER}_all"
rm -rf "$PKG"; mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/netscope" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/metainfo"
cat > "$PKG/DEBIAN/control" <<EOF
Package: netscope
Version: $VER
Section: net
Priority: optional
Architecture: all
Maintainer: miro (hoba101) <hoba101@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: vnstat
Homepage: https://github.com/hoba101/netscope
Description: Professional network usage monitor with history recovery
 NetScope tracks live and historical network usage, integrates with vnStat,
 and can recover old stored vnStat database history when available.
EOF
cp -a "$ROOT/netscope" "$PKG/usr/lib/netscope/"
cat > "$PKG/usr/bin/netscope" <<'EOF'
#!/usr/bin/env bash
export PYTHONPATH=/usr/lib/netscope${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m netscope "$@"
EOF
chmod 755 "$PKG/usr/bin/netscope"
cp "$ROOT/netscope.desktop" "$PKG/usr/share/applications/io.github.hoba101.NetScope.desktop"
cp "$ROOT/assets/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg"
cp "$ROOT/io.github.hoba101.NetScope.metainfo.xml" "$PKG/usr/share/metainfo/io.github.hoba101.NetScope.metainfo.xml"
if command -v dpkg-deb >/dev/null; then
  dpkg-deb --build --root-owner-group "$PKG"
  echo "Built: ${PKG}.deb"
else
  echo "dpkg-deb not found. Package tree prepared at: $PKG"
  echo "Run this script on Debian/Ubuntu or install dpkg-dev."
fi
