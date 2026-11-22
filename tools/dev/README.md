# Development helpers

Scripts used while building wa2html. None of them is needed to use or test the package
(`python -m unittest discover -s tests -t .` is enough); they help with the parts a unit test
cannot see.

| Script | What it does |
| --- | --- |
| `build_windows.sh` | Builds both Windows executables the way `release.yml` does and smoke-tests them. Run from Git Bash: `sh tools/dev/build_windows.sh` (output in `$WA2HTML_BUILD_DIR/out`, default `%TEMP%/wa2html-build/out`). |
| `build_linux.sh` | Builds the Linux program, AppImage, `.deb` and `.rpm` the way `release.yml` does (same pinned tools) and smoke-tests the program and the AppImage. Run on Linux or WSL: `sh tools/dev/build_linux.sh` (files in `$WA2HTML_BUILD_DIR/src/dist/release`, default `~/wa2html-build`); then `sh tools/dev/build_linux.sh --containers` installs and tests the `.deb` and `.rpm` in Docker containers. The packages need the glibc of the machine that built them. |
| `page_check.py` | Opens a generated page through `file://` in headless Edge/Chrome (DevTools protocol), plays the first voice note, checks that a photo and a video load, and saves a screenshot. Usage: `python tools/dev/page_check.py PAGE.html SHOT.png`. |
| `cdpws.py` | The minimal DevTools websocket client used by `page_check.py` (standard library only). |
| `capture_window.ps1` | Starts an executable (optionally with a file, like a drag and drop), captures only its Tk window to a PNG with `PrintWindow`, then closes it. Usage: `powershell -File tools/dev/capture_window.ps1 -Exe wa2html.exe -Arg chat.zip -Png window.png`. |

Use them only with synthetic exports (for example the one in `tests/helpers.py`) or with a real
export that stays on your machine: screenshots of real chats must never be committed.
