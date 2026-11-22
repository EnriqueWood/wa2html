#!/bin/sh
# Build the Linux programs and packages like .github/workflows/release.yml and smoke-test them.
# Run on Linux or WSL:  sh tools/dev/build_linux.sh
# Needs python3 with venv and Tk (python3-venv, python3-tk), xvfb-run (xvfb, xauth), rpmbuild (rpm),
# dpkg-deb, readelf (binutils), desktop-file-validate (desktop-file-utils) and curl.
# The files end up in $WA2HTML_BUILD_DIR/src/dist/release (default ~/wa2html-build).
#
# Then, to install and test the .deb and .rpm in clean containers (needs Docker):
#   sh tools/dev/build_linux.sh --containers
# Note: built on a newer distribution than the release workflow's Ubuntu 22.04, the
# programs need that distribution's newer glibc.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=${WA2HTML_BUILD_DIR:-"$HOME/wa2html-build"}
RELEASE="$WORK/src/dist/release"
WORKFLOW="$REPO/.github/workflows/release.yml"
setting() { sed -n "s/^ *$1: *\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p" "$WORKFLOW"; }  # one source of truth

if [ "${1:-}" = "--containers" ]; then
  cd "$WORK/src"
  for image in debian:stable ubuntu:24.04; do
    docker run --rm -v "$PWD:/w" -w /w "$image" sh packaging/test_linux_package.sh dist/release/wa2html-linux-x64.deb
  done
  for image in fedora:latest opensuse/tumbleweed; do
    docker run --rm -v "$PWD:/w" -w /w "$image" sh packaging/test_linux_package.sh dist/release/wa2html-linux-x64.rpm
  done
  exit 0
fi

PYINSTALLER_VERSION=$(setting PYINSTALLER_VERSION)
rm -rf "$WORK/src"
mkdir -p "$WORK/src" "$WORK/tools"
cd "$REPO"
git -c safe.directory='*' ls-files --cached --others --exclude-standard | tar -cf - -T - | tar -xf - -C "$WORK/src"
if [ ! -x "$WORK/venv/bin/python" ]; then
  python3 -m venv "$WORK/venv"
fi
PY="$WORK/venv/bin/python"
"$PY" -m pip install -q "pyinstaller==$PYINSTALLER_VERSION"
cd "$WORK/src"
"$PY" -m pip install -q --force-reinstall --no-deps .

fetch() {  # url, sha256, file
  if [ ! -f "$3" ] || ! echo "$2  $3" | sha256sum -c --status; then
    curl -fsSL -o "$3" "$1"
  fi
  echo "$2  $3" | sha256sum -c
}
fetch "$(setting APPIMAGETOOL_URL)" "$(setting APPIMAGETOOL_SHA256)" "$WORK/tools/appimagetool"
fetch "$(setting APPIMAGE_RUNTIME_URL)" "$(setting APPIMAGE_RUNTIME_SHA256)" "$WORK/tools/runtime-x86_64"
chmod +x "$WORK/tools/appimagetool"

build() {  # onefile | onedir
  onefile=0; [ "$1" = onefile ] && onefile=1
  WA2HTML_ONEFILE=$onefile "$WORK/venv/bin/pyinstaller" --distpath "dist/$1" --workpath "build/$1" \
    --noconfirm --clean packaging/linux.spec > "$WORK/$1.log" 2>&1 \
    || { echo "BUILD FAILED: $1 (see $WORK/$1.log)"; exit 1; }
  echo "built dist/$1"
}
build onefile
build onedir

desktop-file-validate packaging/linux/wa2html.desktop
"$PY" packaging/linux_packages.py dist/onedir/wa2html "$RELEASE" \
  --appimagetool "$WORK/tools/appimagetool" --runtime "$WORK/tools/runtime-x86_64"
cp dist/onefile/wa2html "$RELEASE/wa2html-linux-x64"

echo "== smoke test: single-file program"
xvfb-run -a "$PY" packaging/smoke_test.py "$RELEASE/wa2html-linux-x64"
echo "== smoke test: AppImage"
xvfb-run -a "$PY" packaging/smoke_test.py "$RELEASE/wa2html-linux-x64.AppImage"
ls -l "$RELEASE"
