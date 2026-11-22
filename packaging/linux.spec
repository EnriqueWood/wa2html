# PyInstaller spec for the Linux programs, the single file and the one-folder build
# (used for the AppImage, .deb and .rpm). From the repository root:
#
#   WA2HTML_ONEFILE=1 pyinstaller --noconfirm --clean packaging/linux.spec   # dist/wa2html
#   pyinstaller --noconfirm --clean packaging/linux.spec                     # dist/wa2html/wa2html
#
# Same as `pyinstaller --collect-data wa2html packaging/wa2html_cli.py`, except that the
# font libraries are left to the system: a bundled fontconfig reads the system's font
# configuration, and an older one cannot parse a newer distribution's (on openSUSE
# Tumbleweed it failed and Tk could not allocate any font, so the window could not open).
# The AppImage project's exclude list leaves these libraries out for the same reason.
import os

from PyInstaller.utils.hooks import collect_data_files

ONEFILE = os.environ.get("WA2HTML_ONEFILE") == "1"
SYSTEM_LIBRARIES = ("libfontconfig.so", "libfreetype.so")

a = Analysis(
    [os.path.join(SPECPATH, "wa2html_cli.py")],
    datas=collect_data_files("wa2html"),
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if not os.path.basename(entry[0]).startswith(SYSTEM_LIBRARIES)]
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="wa2html", console=True, strip=False, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="wa2html", console=True, strip=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="wa2html", strip=False, upx=False)
