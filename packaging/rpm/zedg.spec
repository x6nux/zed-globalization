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
mkdir -p %{buildroot}/usr/lib/zedg
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
mkdir -p %{buildroot}/usr/share/icons/hicolor/1024x1024/apps
cp %{_zedg_dist}/usr/bin/zedg                                      %{buildroot}/usr/bin/
cp %{_zedg_dist}/usr/libexec/zedg                                  %{buildroot}/usr/libexec/
cp %{_zedg_dist}/usr/lib/zedg/libgit2.so.1.8                       %{buildroot}/usr/lib/zedg/ 2>/dev/null || true
cp %{_zedg_dist}/usr/share/applications/zedg.desktop               %{buildroot}/usr/share/applications/
cp %{_zedg_dist}/usr/share/icons/hicolor/512x512/apps/zedg.png     %{buildroot}/usr/share/icons/hicolor/512x512/apps/
cp %{_zedg_dist}/usr/share/icons/hicolor/1024x1024/apps/zedg.png   %{buildroot}/usr/share/icons/hicolor/1024x1024/apps/
# issue #37: ecosystem tools and desktop "default editor" look for `zed`
ln -sf zedg %{buildroot}/usr/bin/zed
ln -sf zedg %{buildroot}/usr/libexec/zed-cli
cp %{_zedg_dist}/usr/bin/zedg-activate                           %{buildroot}/usr/bin/

%post
ldconfig
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi

%files
%attr(755, root, root) /usr/bin/zedg
%attr(755, root, root) /usr/libexec/zedg
%attr(755, root, root) /usr/bin/zedg-activate
/usr/bin/zed
/usr/libexec/zed-cli
/usr/lib/zedg/
/usr/share/applications/zedg.desktop
/usr/share/icons/hicolor/512x512/apps/zedg.png
/usr/share/icons/hicolor/1024x1024/apps/zedg.png
