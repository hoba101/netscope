Name:           netscope
Version:        1.0.0
Release:        1%{?dist}
Summary:        Professional network usage monitor with history recovery

License:        GPL-3.0-or-later
URL:            https://github.com/hoba101/netscope
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Recommends:     vnstat

%description
NetScope tracks live and historical network usage, integrates with vnStat,
and can recover old stored vnStat database history when available.

%prep
%autosetup

%install
mkdir -p %{buildroot}/usr/lib/netscope %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications %{buildroot}%{_datadir}/icons/hicolor/scalable/apps %{buildroot}%{_datadir}/metainfo
cp -a netscope %{buildroot}/usr/lib/netscope/
cat > %{buildroot}%{_bindir}/netscope <<'EOF'
#!/usr/bin/bash
export PYTHONPATH=/usr/lib/netscope${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m netscope "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/netscope
install -m 0644 netscope.desktop %{buildroot}%{_datadir}/applications/io.github.hoba101.NetScope.desktop
install -m 0644 assets/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg
install -m 0644 io.github.hoba101.NetScope.metainfo.xml %{buildroot}%{_datadir}/metainfo/io.github.hoba101.NetScope.metainfo.xml

%files
%license LICENSE
%doc README.md
%{_bindir}/netscope
/usr/lib/netscope/netscope
%{_datadir}/applications/io.github.hoba101.NetScope.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.hoba101.NetScope.svg
%{_datadir}/metainfo/io.github.hoba101.NetScope.metainfo.xml

%changelog
* Mon Nov 09 2026 miro (hoba101) <hoba101@users.noreply.github.com> - 1.0.0-1
- Initial professional release
