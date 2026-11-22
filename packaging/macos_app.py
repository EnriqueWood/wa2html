"""macOS packaging: the app icon, the finished wa2html.app and the .dmg disk image.

    python packaging/macos_app.py icon build/wa2html.icns
    python packaging/macos_app.py dmg dist/wa2html.app dist/wa2html-macos-arm64.dmg
    python packaging/macos_app.py check-dmg dist/wa2html-macos-arm64.dmg

`icon` draws the icon at every size macOS uses and packs it with iconutil.
`dmg` writes the version into the app's Info.plist, signs the app again (ad hoc,
as PyInstaller does: Apple silicon only runs signed code), checks the signature
and puts the app in a disk image next to a link to the Applications folder.
`check-dmg` mounts the image and runs the smoke test on the app inside it.

Run on macOS from the repository root. Uses only tools that come with macOS
(iconutil, plutil, codesign, hdiutil).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wa2html import __version__  # noqa: E402
from wa2html.icon import png  # noqa: E402

BUNDLE_ID = "io.github.enriquewood.wa2html"
# iconutil expects these files in an .iconset folder.
ICONSET = {f"icon_{s}x{s}.png": s for s in (16, 32, 128, 256, 512)}
ICONSET.update({f"icon_{s}x{s}@2x.png": s * 2 for s in (16, 32, 128, 256, 512)})


def run(cmd) -> None:
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)


def make_icon(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "wa2html.iconset"
        iconset.mkdir()
        cache: dict[int, bytes] = {}
        for name, size in ICONSET.items():
            if size not in cache:
                cache[size] = png(size)
            (iconset / name).write_bytes(cache[size])
        run(["iconutil", "--convert", "icns", "--output", out, iconset])
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


def finish_app(app: Path) -> None:
    plist = app / "Contents" / "Info.plist"
    for key, kind, value in (
        ("CFBundleShortVersionString", "string", __version__),
        ("CFBundleVersion", "string", __version__),
        ("CFBundleDisplayName", "string", "wa2html"),
        ("LSApplicationCategoryType", "string", "public.app-category.utilities"),
        ("NSHumanReadableCopyright", "string", "MIT licence - https://github.com/EnriqueWood/wa2html"),
    ):
        run(["plutil", "-replace", key, f"-{kind}", value, plist])
    # Changing Info.plist breaks the seal PyInstaller signed; sign the bundle again.
    run(["codesign", "--force", "--sign", "-", app])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])


def make_dmg(app: Path, out: Path) -> None:
    finish_app(app)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "wa2html"
        stage.mkdir()
        run(["ditto", app, stage / app.name])  # ditto keeps the bundle's links and signature intact
        (stage / "Applications").symlink_to("/Applications")
        create = ["hdiutil", "create", "-volname", "wa2html", "-srcfolder", stage, "-fs", "HFS+", "-format", "UDZO",
                  "-ov", out]
        for attempt in range(1, 4):  # hdiutil sometimes fails with "Resource busy" on CI machines
            try:
                run(create)
                break
            except subprocess.CalledProcessError:
                if attempt == 3:
                    raise
                print(f"hdiutil failed (attempt {attempt}), retrying in 5 s", flush=True)
                time.sleep(5)
    run(["hdiutil", "verify", out])
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


def check_dmg(dmg: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        mount = Path(tmp) / "mnt"
        mount.mkdir()
        run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, dmg])
        try:
            app = mount / "wa2html.app"
            if not (mount / "Applications").is_symlink():
                raise SystemExit("FAILED: the disk image has no link to Applications")
            run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])
            version = subprocess.run(
                ["plutil", "-extract", "CFBundleShortVersionString", "raw", app / "Contents" / "Info.plist"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if version != __version__:
                raise SystemExit(f"FAILED: the app says version {version}, expected {__version__}")
            run([sys.executable, ROOT / "packaging" / "smoke_test.py", app / "Contents" / "MacOS" / "wa2html"])
        finally:
            run(["hdiutil", "detach", mount])
    print("disk image check passed")


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["icon"] and len(args) == 2:
        make_icon(Path(args[1]))
    elif args[:1] == ["dmg"] and len(args) == 3:
        make_dmg(Path(args[1]), Path(args[2]))
    elif args[:1] == ["check-dmg"] and len(args) == 2:
        check_dmg(Path(args[1]))
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
