#!/bin/sh
# Install a wa2html .deb or .rpm in a clean container, smoke-test it (the command line
# and the window, on a virtual display) and remove it again. Used by
# .github/workflows/release.yml, from the repository root:
#
#   docker run --rm -v "$PWD:/w" -w /w debian:stable sh packaging/test_linux_package.sh dist/release/wa2html-linux-x64.deb
set -eu
pkg=$1
export PYTHONDONTWRITEBYTECODE=1

install_pkg() {
  case "$pkg" in
    *.deb)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq "./$pkg" python3 xvfb xauth > /dev/null
      ;;
    *.rpm)
      if command -v dnf > /dev/null; then
        dnf install -y -q "./$pkg" python3 xorg-x11-server-Xvfb xauth
      else
        zypper --non-interactive --quiet install --allow-unsigned-rpm "./$pkg" python3 xvfb-run
      fi
      ;;
    *) echo "not a .deb or .rpm: $pkg"; exit 2 ;;
  esac
}

remove_pkg() {
  case "$pkg" in
    *.deb) apt-get remove -y -qq wa2html > /dev/null ;;
    *.rpm)
      if command -v dnf > /dev/null; then dnf remove -y -q wa2html; else zypper --non-interactive --quiet remove wa2html; fi
      ;;
  esac
}

install_pkg
test -x /usr/bin/wa2html
test -f /usr/share/applications/wa2html.desktop
test -f /usr/share/icons/hicolor/256x256/apps/wa2html.png
xvfb-run -a python3 packaging/smoke_test.py /usr/bin/wa2html > /tmp/smoke.log 2>&1 || { cat /tmp/smoke.log; exit 1; }
tail -3 /tmp/smoke.log
# The package must bring in the font configuration the bundled fontconfig reads.
if grep -q "Fontconfig error" /tmp/smoke.log; then
  grep "Fontconfig error" /tmp/smoke.log | head -3
  echo "FAILED: fontconfig found no configuration"
  exit 1
fi
remove_pkg
test ! -e /usr/lib/wa2html
test ! -e /usr/bin/wa2html
echo "package test passed: $pkg on $(. /etc/os-release && echo "$PRETTY_NAME")"
