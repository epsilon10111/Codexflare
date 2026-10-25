Name:           codexflare
Version:        0.1.1
Release:        1
Summary:        Local startup animation and background editor for Codex
License:        MIT AND LicenseRef-Codexflare-Media
URL:            https://github.com/epsilon10111/Codexflare
Source0:        %{url}/releases/download/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3 >= 3.11
BuildRequires:  desktop-file-utils
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       gtk3
Requires:       webkit2gtk4.1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       coreutils
Recommends:     ffmpeg-free

# Ship portable sources without interpreter-version-specific bytecode.
%global __brp_python_bytecompile %{nil}
%global debug_package %{nil}

%description
Codexflare is a local GTK/WebKit editor for custom startup videos and PNG
workspace backgrounds. It creates a reversible per-user copy of an existing
Linux Codex installation. It does not include or modify the system Codex app.
Patching currently supports Codex 26.1002.52244, build 13536, on x86_64 only.
The editor can preview and save settings without a compatible Codex install.

%prep
%setup -q
cp assets/LICENSE MEDIA-LICENSE

%build
# Python and static assets do not require compilation.

%install
install -d %{buildroot}%{_datadir}/%{name}/{tools,src,ui,assets}
for file in animation background desktop editor manage patch_app paths; do
    install -m 0644 tools/$file.py %{buildroot}%{_datadir}/%{name}/tools/
done
sed -i '1{/^#!/d;}' %{buildroot}%{_datadir}/%{name}/tools/*.py
install -m 0644 src/* %{buildroot}%{_datadir}/%{name}/src/
install -m 0644 ui/* %{buildroot}%{_datadir}/%{name}/ui/
install -m 0644 assets/default.webm assets/default1.png assets/default2.png %{buildroot}%{_datadir}/%{name}/assets/
install -m 0644 VERSION %{buildroot}%{_datadir}/%{name}/
echo '%{name} %{version}' > %{buildroot}%{_datadir}/%{name}/.packaged
install -Dpm 0755 packaging/codexflare %{buildroot}%{_bindir}/codexflare
install -Dpm 0755 packaging/codexflare-manage %{buildroot}%{_bindir}/codexflare-manage
install -Dpm 0644 packaging/codexflare.desktop %{buildroot}%{_datadir}/applications/codexflare.desktop
install -Dpm 0644 ui/mark.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/codexflare.svg
install -Dpm 0644 packaging/codexflare.1 %{buildroot}%{_mandir}/man1/codexflare.1
install -Dpm 0644 packaging/codexflare-manage.1 %{buildroot}%{_mandir}/man1/codexflare-manage.1

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/codexflare.desktop
# Parse without generating bytecode in the payload.
python3 -c 'import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path("%{buildroot}%{_datadir}/%{name}/tools").glob("*.py")]'

%files
%license LICENSE MEDIA-LICENSE THIRD_PARTY_NOTICES.md
%doc README.md
%{_bindir}/codexflare
%{_bindir}/codexflare-manage
%{_datadir}/%{name}/
%{_datadir}/applications/codexflare.desktop
%{_datadir}/icons/hicolor/scalable/apps/codexflare.svg
%{_mandir}/man1/codexflare.1*
%{_mandir}/man1/codexflare-manage.1*

%changelog
* Sun Oct 25 2026 epsilon10111 - 0.1.1-1
- macOS build 20586 release; no new RPM published for this version.

* Sun Oct 25 2026 epsilon10111 - 0.1.0-1
- Initial RPM with per-user settings and reversible Codex customization.
