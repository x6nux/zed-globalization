Name:           zedg
Version:        %{_zedg_version}
Release:        1%{?dist}
Summary:        Zed editor with globalization support
License:        AGPL-3.0-or-later AND Apache-2.0 AND GPL-3.0-or-later
URL:            https://github.com/x6nux/zed-globalization

AutoReqProv:    no

%description
A high-performance, multiplayer code editor with globalization support.

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/libexec
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
mkdir -p %{buildroot}/usr/share/icons/hicolor/1024x1024/apps
cp %{_zedg_dist}/usr/bin/zedg                                      %{buildroot}/usr/bin/
cp %{_zedg_dist}/usr/libexec/zedg                                  %{buildroot}/usr/libexec/
cp %{_zedg_dist}/usr/share/applications/zedg.desktop               %{buildroot}/usr/share/applications/
cp %{_zedg_dist}/usr/share/icons/hicolor/512x512/apps/zedg.png     %{buildroot}/usr/share/icons/hicolor/512x512/apps/
cp %{_zedg_dist}/usr/share/icons/hicolor/1024x1024/apps/zedg.png   %{buildroot}/usr/share/icons/hicolor/1024x1024/apps/

%files
%attr(755, root, root) /usr/bin/zedg
%attr(755, root, root) /usr/libexec/zedg
/usr/share/applications/zedg.desktop
/usr/share/icons/hicolor/512x512/apps/zedg.png
/usr/share/icons/hicolor/1024x1024/apps/zedg.png
