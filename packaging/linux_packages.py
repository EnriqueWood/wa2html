"""Build the Linux packages (AppImage, .deb and .rpm) from a PyInstaller one-folder build.

    python packaging/linux_packages.py dist-onedir/wa2html OUT_DIR \\
        --appimagetool PATH --runtime PATH [--formats appimage deb rpm]

The one-folder build (``pyinstaller --onedir``) goes to /usr/lib/wa2html, with
/usr/bin/wa2html pointing to it, a menu entry and the icon. The same tree is the
AppImage's AppDir. The system libraries the build needs (the ones PyInstaller does
not bundle, such as glibc) are read from the binaries with readelf and become the
package dependencies.

Run it on Linux from the repository root. It needs readelf (binutils), dpkg-deb and
dpkg (for .deb), rpmbuild (for .rpm; package ``rpm`` on Ubuntu), and appimagetool
plus an AppImage runtime file (for the AppImage; see .github/workflows/release.yml).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wa2html import __version__  # noqa: E402
from wa2html.icon import png  # noqa: E402

NAME = "wa2html"
HOMEPAGE = "https://github.com/EnriqueWood/wa2html"
SUMMARY = "Turn a WhatsApp chat export into a web page that looks like WhatsApp"
DESCRIPTION = (
    "wa2html turns a WhatsApp chat export into one HTML page that looks and works like\n"
    "WhatsApp: voice notes play in the browser, photos, stickers and videos appear in the\n"
    "conversation, and the page works offline. Nothing is lost: every message and file of\n"
    "the export is checked with SHA-256 after the page is written."
)
DESKTOP_FILE = ROOT / "packaging" / "linux" / "wa2html.desktop"
ICON_SIZES = (16, 32, 48, 64, 128, 256)
ASSET = "wa2html-linux-x64"

GLIBC = re.compile(r"GLIBC_(\d+(?:\.\d+)+)$")

# The window draws text with the system's fontconfig (packaging/linux.spec does not bundle
# it), which needs its configuration and at least one real font: without them Tk cannot
# allocate a font (seen on minimal Fedora and openSUSE). On Debian/Ubuntu, fontconfig
# brings a font itself. RPM distributions name the same fonts differently, and the generic
# font(:lang=en) is also provided by packages without usable fonts (xterm on openSUSE), so
# the .rpm asks for one of a few common font packages (any one already installed is enough).
DEB_EXTRA_DEPENDS = ("fontconfig",)
RPM_EXTRA_REQUIRES = ("fontconfig", "(dejavu-sans-fonts or dejavu-fonts or google-noto-sans-fonts)")


def run(cmd, quiet: bool = False, **kwargs) -> str:
    if not quiet:
        print("+", " ".join(map(str, cmd)), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        raise SystemExit(f"FAILED (exit {proc.returncode}): {' '.join(map(str, cmd))}")
    return proc.stdout


# ---------------------------------------------------------------- dependencies


def parse_needed(readelf_dynamic: str) -> list[str]:
    """Library names from ``readelf -d`` output (its NEEDED entries)."""
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", readelf_dynamic)


def parse_version_needs(readelf_versions: str) -> dict[str, set[str]]:
    """{library: {symbol version, ...}} from ``readelf -V`` output (its version needs)."""
    needs: dict[str, set[str]] = {}
    current = None
    for line in readelf_versions.splitlines():
        file_match = re.search(r"\bFile: (\S+)", line)
        if file_match:
            current = file_match.group(1)
            needs.setdefault(current, set())
            continue
        name_match = re.search(r"\bName: (\S+)", line)
        if name_match and current:
            needs[current].add(name_match.group(1))
    return needs


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def newest_glibc(versions) -> str | None:
    found = [m.group(1) for v in versions for m in [GLIBC.match(v)] if m]
    return max(found, key=version_key) if found else None


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def system_libraries(dist: Path) -> dict[str, str | None]:
    """{library: newest glibc symbol version it is needed at (or None)} for every
    library the build needs but does not contain."""
    files = [p for p in dist.rglob("*") if p.is_file() and not p.is_symlink() and is_elf(p)]
    bundled = {p.name for p in dist.rglob("*")}
    libraries: dict[str, set[str]] = {}
    for path in files:
        for lib in parse_needed(run(["readelf", "-d", path], quiet=True)):
            if lib not in bundled:
                libraries.setdefault(lib, set())
        for lib, versions in parse_version_needs(run(["readelf", "-V", path], quiet=True)).items():
            if lib not in bundled:
                libraries.setdefault(lib, set()).update(versions)
    return {lib: newest_glibc(versions) for lib, versions in sorted(libraries.items())}


def parse_dpkg_search(output: str, library: str) -> str | None:
    """The package owning `library` in ``dpkg -S`` output, preferring the x86-64 copy.

    Lines look like ``libc6:amd64: /usr/lib/x86_64-linux-gnu/libc.so.6`` (several
    owners are separated by ", ").
    """
    matches = []
    for line in output.splitlines():
        owners, sep, path = line.rpartition(": ")
        if sep and not owners.startswith("diversion") and Path(path.strip()).name == library:
            package = owners.split(",")[0].strip().split(":")[0]
            matches.append((("x86_64" not in path) + ("i386" in owners), package))
    return min(matches)[1] if matches else None


def debian_package_of(library: str) -> str:
    """The Debian/Ubuntu package that provides `library` on this machine (dpkg -S)."""
    # A pattern: a plain path starting with "/" would have to match exactly.
    package = parse_dpkg_search(run(["dpkg", "-S", f"*/{library}"], quiet=True), library)
    if not package:
        raise SystemExit(f"no installed package provides {library}")
    return package


def deb_depends(libraries: dict[str, str | None], package_of=debian_package_of) -> str:
    """The Depends field: one package per library, the C library at the needed version,
    plus the font configuration."""
    glibc = newest_glibc(f"GLIBC_{v}" for v in libraries.values() if v)
    packages = sorted({package_of(lib) for lib in libraries} | set(DEB_EXTRA_DEPENDS))
    return ", ".join(f"{p} (>= {glibc})" if p == "libc6" and glibc else p for p in packages)


def rpm_requires(libraries: dict[str, str | None]) -> list[str]:
    """Requires by library name, which works on every RPM distribution (Fedora, openSUSE...)."""
    requires = []
    for lib, glibc in libraries.items():
        requires.append(f"{lib}()(64bit)")
        if glibc:
            requires.append(f"{lib}(GLIBC_{glibc})(64bit)")
    return requires + list(RPM_EXTRA_REQUIRES)


# ---------------------------------------------------------------- the file tree


def stage(dist: Path, root: Path) -> None:
    """Lay out the installed files under `root` (root/usr/...)."""
    lib = root / "usr" / "lib" / NAME
    shutil.copytree(dist, lib, symlinks=True)
    (lib / NAME).chmod(0o755)
    bin_dir = root / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / NAME).symlink_to(f"../lib/{NAME}/{NAME}")
    apps = root / "usr" / "share" / "applications"
    apps.mkdir(parents=True)
    shutil.copyfile(DESKTOP_FILE, apps / f"{NAME}.desktop")
    for size in ICON_SIZES:
        icon_dir = root / "usr" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
        icon_dir.mkdir(parents=True)
        (icon_dir / f"{NAME}.png").write_bytes(png(size))
    doc = root / "usr" / "share" / "doc" / NAME
    doc.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", doc / "LICENSE")
    # Standard permissions whatever the umask of the build machine: 755 for folders and
    # programs, 644 for everything else.
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir() or path.stat().st_mode & 0o111:
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def installed_size_kib(root: Path) -> int:
    total = sum(p.lstat().st_size for p in root.rglob("*") if p.is_file() or p.is_symlink())
    return (total + 1023) // 1024


# ---------------------------------------------------------------- packages


def deb_control(version: str, depends: str, installed_size: int) -> str:
    description = "\n".join(" " + (line or ".") for line in DESCRIPTION.splitlines())
    return (
        f"Package: {NAME}\n"
        f"Version: {version}\n"
        "Architecture: amd64\n"
        f"Maintainer: EnriqueWood <{HOMEPAGE}>\n"
        f"Installed-Size: {installed_size}\n"
        f"Depends: {depends}\n"
        "Section: utils\n"
        "Priority: optional\n"
        f"Homepage: {HOMEPAGE}\n"
        f"Description: {SUMMARY}\n"
        f"{description}\n"
    )


def build_deb(root: Path, out: Path, version: str, depends: str, work: Path) -> Path:
    tree = work / "deb"
    shutil.copytree(root, tree, symlinks=True)
    control = tree / "DEBIAN"
    control.mkdir()
    control.chmod(0o755)
    (control / "control").write_text(deb_control(version, depends, installed_size_kib(root)), encoding="utf-8")
    target = out / f"{ASSET}.deb"
    # xz rather than the newer default zstd, which older dpkg versions cannot read.
    run(["dpkg-deb", "-Zxz", "--root-owner-group", "--build", tree, target])
    print(run(["dpkg-deb", "--info", target]))
    return target


def rpm_spec(version: str, requires: list[str], root: Path) -> str:
    requires_lines = "".join(f"Requires: {r}\n" for r in requires)
    return (
        f"Name: {NAME}\n"
        f"Version: {version}\n"
        "Release: 1\n"
        f"Summary: {SUMMARY}\n"
        "License: MIT\n"
        f"URL: {HOMEPAGE}\n"
        # The build bundles Python and its libraries: no automatic dependencies from them,
        # no stripping (it would break the PyInstaller executable), no debug package.
        "AutoReqProv: no\n"
        f"{requires_lines}"
        "%global debug_package %{nil}\n"
        "%global __os_install_post %{nil}\n"
        "%global _build_id_links none\n"
        "%define _binary_payload w9.xzdio\n"
        "\n"
        "%description\n"
        f"{DESCRIPTION}\n"
        "\n"
        "%install\n"
        f"cp -a '{root}/.' %{{buildroot}}/\n"
        "\n"
        "%files\n"
        f"/usr/lib/{NAME}\n"
        f"/usr/bin/{NAME}\n"
        f"/usr/share/applications/{NAME}.desktop\n"
        f"/usr/share/icons/hicolor/*/apps/{NAME}.png\n"
        f"/usr/share/doc/{NAME}\n"
    )


def build_rpm(root: Path, out: Path, version: str, requires: list[str], work: Path) -> Path:
    top = work / "rpmbuild"
    (top / "SPECS").mkdir(parents=True)
    spec = top / "SPECS" / f"{NAME}.spec"
    spec.write_text(rpm_spec(version, requires, root), encoding="utf-8")
    run(["rpmbuild", "-bb", "--define", f"_topdir {top}", "--target", "x86_64", spec])
    built = next((top / "RPMS").rglob("*.rpm"))
    target = out / f"{ASSET}.rpm"
    shutil.move(str(built), target)
    print(run(["rpm", "-qip", target]))
    print(run(["rpm", "-qp", "--requires", target]))
    return target


def build_appimage(root: Path, out: Path, appimagetool: Path, runtime: Path, work: Path) -> Path:
    appdir = work / "AppDir"
    shutil.copytree(root, appdir, symlinks=True)
    (appdir / "AppRun").symlink_to(f"usr/lib/{NAME}/{NAME}")
    shutil.copyfile(DESKTOP_FILE, appdir / f"{NAME}.desktop")
    (appdir / f"{NAME}.png").write_bytes(png(256))
    (appdir / ".DirIcon").symlink_to(f"{NAME}.png")
    target = out / f"{ASSET}.AppImage"
    env = dict(os.environ, ARCH="x86_64")
    # --appimage-extract-and-run: appimagetool is itself an AppImage and the build
    # machine may have no FUSE.
    print(run([appimagetool, "--appimage-extract-and-run", "--no-appstream", "--runtime-file", runtime,
               appdir, target], env=env))
    target.chmod(0o755)
    return target


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dist", type=Path, help="the PyInstaller one-folder build (dist-onedir/wa2html)")
    p.add_argument("out", type=Path, help="where to write the packages")
    p.add_argument("--formats", nargs="+", choices=("appimage", "deb", "rpm"), default=["appimage", "deb", "rpm"])
    p.add_argument("--appimagetool", type=Path, help="appimagetool executable (for the AppImage)")
    p.add_argument("--runtime", type=Path, help="AppImage runtime file (for the AppImage)")
    args = p.parse_args(argv)
    if "appimage" in args.formats and not (args.appimagetool and args.runtime):
        p.error("the AppImage needs --appimagetool and --runtime")
    dist = args.dist.resolve()
    if not (dist / NAME).is_file():
        p.error(f"{dist} is not a PyInstaller one-folder build of {NAME}")
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out.resolve()

    libraries = system_libraries(dist)
    print("System libraries needed:", ", ".join(f"{k} ({v})" if v else k for k, v in libraries.items()))

    with tempfile.TemporaryDirectory(prefix="wa2html-pkg-") as tmp:
        work = Path(tmp)
        root = work / "root"
        stage(dist, root)
        built = []
        if "deb" in args.formats:
            built.append(build_deb(root, out, __version__, deb_depends(libraries), work))
        if "rpm" in args.formats:
            built.append(build_rpm(root, out, __version__, rpm_requires(libraries), work))
        if "appimage" in args.formats:
            built.append(build_appimage(root, out, args.appimagetool.resolve(), args.runtime.resolve(), work))
    for path in built:
        print(f"built {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
