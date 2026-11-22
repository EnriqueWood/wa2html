#!/bin/sh
# Build both Windows executables like .github/workflows/release.yml and smoke-test them.
# Run from Git Bash on Windows:  sh tools/dev/build_windows.sh
# It copies the repository to a short path first: very long paths break `pip install .`
# on Windows (MAX_PATH), and PyInstaller's work files stay out of the repository.
set -e
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=${WA2HTML_BUILD_DIR:-"${TEMP:-/tmp}/wa2html-build"}
PYINSTALLER_VERSION=6.22.3

rm -rf "$WORK/src" "$WORK/out"
mkdir -p "$WORK/src" "$WORK/out"
if [ ! -x "$WORK/venv/Scripts/python.exe" ]; then
  python -m venv "$WORK/venv"
fi
PY="$WORK/venv/Scripts/python.exe"
"$PY" -m pip install -q "pyinstaller==$PYINSTALLER_VERSION"

cd "$REPO"
git ls-files --cached --others --exclude-standard | tar -cf - -T - | tar -xf - -C "$WORK/src"
cd "$WORK/src"
"$PY" -m pip install -q --force-reinstall --no-deps .
"$PY" packaging/make_icon.py build/wa2html.ico

build() {  # entry script, output name, extra PyInstaller arguments
  "$WORK/venv/Scripts/pyinstaller.exe" --onefile --name wa2html --collect-data wa2html $3 \
    --noconfirm --clean "$1" > "$WORK/out/$2.log" 2>&1 || { echo "BUILD FAILED: $2 (see $WORK/out/$2.log)"; exit 1; }
  mv dist/wa2html.exe "$WORK/out/$2"
  echo "built $WORK/out/$2"
}
build packaging/wa2html_gui.py wa2html-windows-x64.exe "--windowed --icon build/wa2html.ico"
build packaging/wa2html_cli_windows.py wa2html-cli-windows-x64.exe "--icon build/wa2html.ico"

echo "== smoke test: window-only executable"
"$PY" packaging/smoke_test.py "$WORK/out/wa2html-windows-x64.exe" --gui-only
echo "== smoke test: command-line executable"
"$PY" packaging/smoke_test.py "$WORK/out/wa2html-cli-windows-x64.exe"
