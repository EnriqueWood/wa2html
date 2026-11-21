"""Smoke test for a built wa2html executable.

Builds a synthetic export (made-up names, generated media) with the test
helpers, runs the executable on it in both modes and checks that it reports a
successful verification and that the page carries its assets and the Lottie
player. Then it opens the window in self-test mode. Usage, from the
repository root (on Linux, inside xvfb-run when there is no display):

    python packaging/smoke_test.py dist/wa2html.exe [--no-gui | --gui-only]

--gui-only is for the window-only Windows program, which has no console.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import IOS_CHAT, IOS_FILES, make_zip  # noqa: E402


def run(cmd):
    # No stdin: the Windows build must never wait for Enter when it is not run by double-click.
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    output = proc.stdout + proc.stderr
    print(output)
    if proc.returncode != 0:
        raise SystemExit(f"FAILED (exit {proc.returncode}): {' '.join(map(str, cmd))}")
    return output


def gui_only(exe: Path) -> None:
    """The window-only Windows program has no console: judge it by its exit code."""
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = make_zip(Path(tmp) / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)
        proc = subprocess.run([exe, "--gui-selftest", zip_path], stdin=subprocess.DEVNULL, timeout=300)
        if proc.returncode != 0:
            raise SystemExit(f"FAILED: window self-test exited with {proc.returncode}")
    print("smoke test passed (window-only program)")


def main() -> None:
    exe = Path(sys.argv[1]).resolve()
    if "--gui-only" in sys.argv:
        gui_only(exe)
        return
    version = run([exe, "--version"])
    if "wa2html" not in version:
        raise SystemExit("FAILED: --version does not print the program name")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        zip_path = make_zip(tmp / "WhatsApp Chat - Bob.zip", IOS_CHAT, IOS_FILES)

        out = run([exe, zip_path])
        if "Verified" not in out:
            raise SystemExit("FAILED: no successful verification in the output")
        page = (tmp / "WhatsApp Chat - Bob.html").read_text(encoding="utf-8")
        for needle in ("wa-config", "class=\"voice\"", "lottie-web 5.12.2", "Content-Security-Policy"):
            if needle not in page:
                raise SystemExit(f"FAILED: {needle!r} missing from the generated page")

        out = run([exe, zip_path, "--mode", "folder", "-o", tmp / "viewer"])
        if "Verified" not in out or not (tmp / "viewer" / "media").is_dir():
            raise SystemExit("FAILED: folder mode")

        if "--no-gui" not in sys.argv:
            # Opens the window (Tk must be bundled) and converts through it.
            out = run([exe, "--gui-selftest", zip_path])
            if "gui selftest passed" not in out:
                raise SystemExit("FAILED: the window")
    print("smoke test passed")


if __name__ == "__main__":
    main()
