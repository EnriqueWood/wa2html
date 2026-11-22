"""Tests for the packaging scripts (the parts that do not need the packaging tools)."""

from __future__ import annotations

import configparser
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from wa2html import __version__
from wa2html.i18n import LANGUAGES

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


linux = load("linux_packages")
macos = load("macos_app")

READELF_DYNAMIC = """
Dynamic section at offset 0x2dd8 contains 28 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libpython3.12.so.1.0]
 0x0000000000000001 (NEEDED)             Shared library: [libm.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000000c (INIT)               0x1000
"""

READELF_VERSIONS = """
Version symbols section '.gnu.version' contains 40 entries:
 Addr: 0x0000000000000a10  Offset: 0x000a10  Link: 6 (.dynsym)
  000:   0 (*local*)       2 (GLIBC_2.2.5)   3 (GLIBC_2.29)

Version needs section '.gnu.version_r' contains 2 entries:
 Addr: 0x0000000000000b10  Offset: 0x000b10  Link: 7 (.dynstr)
  000000: Version: 1  File: libm.so.6  Cnt: 1
  0x0010:   Name: GLIBC_2.29  Flags: none  Version: 3
  0x0020: Version: 1  File: libc.so.6  Cnt: 3
  0x0030:   Name: GLIBC_2.34  Flags: none  Version: 5
  0x0040:   Name: GLIBC_2.2.5  Flags: none  Version: 2
  0x0050:   Name: GLIBC_2.14  Flags: none  Version: 4
"""


class LinuxDependencies(unittest.TestCase):
    def test_needed_libraries(self):
        self.assertEqual(linux.parse_needed(READELF_DYNAMIC), ["libpython3.12.so.1.0", "libm.so.6", "libc.so.6"])

    def test_version_needs(self):
        needs = linux.parse_version_needs(READELF_VERSIONS)
        self.assertEqual(needs, {"libm.so.6": {"GLIBC_2.29"}, "libc.so.6": {"GLIBC_2.34", "GLIBC_2.2.5", "GLIBC_2.14"}})

    def test_newest_glibc_compares_numerically(self):
        self.assertEqual(linux.newest_glibc({"GLIBC_2.9", "GLIBC_2.14", "GLIBC_2.2.5"}), "2.14")
        self.assertIsNone(linux.newest_glibc({"GCC_3.0"}))

    def test_dpkg_search(self):
        output = (
            "libc6:i386: /usr/lib/i386-linux-gnu/libc.so.6\n"
            "libc6:amd64: /usr/lib/x86_64-linux-gnu/libc.so.6\n"
            "libc6-dbg:amd64: /usr/lib/debug/libc.so.6.debug\n"
        )
        self.assertEqual(linux.parse_dpkg_search(output, "libc.so.6"), "libc6")
        self.assertEqual(
            linux.parse_dpkg_search("libxcb1:amd64: /usr/lib/x86_64-linux-gnu/libxcb.so.1\n", "libxcb.so.1"), "libxcb1"
        )
        self.assertIsNone(linux.parse_dpkg_search("", "libfoo.so.1"))

    def test_deb_depends(self):
        packages = {"libc.so.6": "libc6", "libm.so.6": "libc6", "libxcb.so.1": "libxcb1"}
        depends = linux.deb_depends(
            {"libc.so.6": "2.34", "libm.so.6": "2.29", "libxcb.so.1": None}, package_of=packages.__getitem__
        )
        self.assertEqual(depends, "fontconfig, libc6 (>= 2.34), libxcb1")

    def test_rpm_requires_use_library_names(self):
        requires = linux.rpm_requires({"libc.so.6": "2.34", "libxcb.so.1": None})
        self.assertEqual(
            requires,
            [
                "libc.so.6()(64bit)",
                "libc.so.6(GLIBC_2.34)(64bit)",
                "libxcb.so.1()(64bit)",
                "fontconfig",
                "(dejavu-sans-fonts or dejavu-fonts or google-noto-sans-fonts)",
            ],
        )


class LinuxPackageFiles(unittest.TestCase):
    def test_deb_control(self):
        control = linux.deb_control("1.2.3", "libc6 (>= 2.34)", 4096)
        fields = dict(line.split(": ", 1) for line in control.splitlines() if not line.startswith(" "))
        self.assertEqual(fields["Package"], "wa2html")
        self.assertEqual(fields["Version"], "1.2.3")
        self.assertEqual(fields["Architecture"], "amd64")
        self.assertEqual(fields["Depends"], "libc6 (>= 2.34)")
        self.assertEqual(fields["Installed-Size"], "4096")
        self.assertTrue(control.endswith("\n"))
        long_description = [line for line in control.splitlines() if line.startswith(" ")]
        self.assertTrue(long_description)

    def test_rpm_spec(self):
        spec = linux.rpm_spec("1.2.3", ["libc.so.6()(64bit)"], Path("/tmp/root"))
        self.assertIn("Version: 1.2.3\n", spec)
        self.assertIn("AutoReqProv: no\n", spec)
        self.assertIn("Requires: libc.so.6()(64bit)\n", spec)
        self.assertIn("%global __os_install_post %{nil}\n", spec)  # never strip the executable
        self.assertIn("/usr/bin/wa2html\n", spec)

    def test_desktop_entry(self):
        entry = configparser.ConfigParser(interpolation=None)
        entry.optionxform = str
        entry.read(linux.DESKTOP_FILE, encoding="utf-8")
        section = entry["Desktop Entry"]
        self.assertEqual(section["Type"], "Application")
        self.assertEqual(section["Exec"], "wa2html --gui")
        self.assertEqual(section["Icon"], "wa2html")
        self.assertEqual(section["Terminal"], "false")
        for lang in LANGUAGES:
            if lang != "en":
                self.assertIn(f"Comment[{lang}]", section)

    @unittest.skipIf(sys.platform == "win32", "symbolic links need extra rights on Windows")
    def test_stage_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            (dist / "_internal").mkdir(parents=True)
            (dist / "wa2html").write_bytes(b"\x7fELF")
            (dist / "_internal" / "libpython3.12.so.1.0").write_bytes(b"\x7fELF")
            root = Path(tmp) / "root"
            linux.stage(dist, root)
            self.assertTrue((root / "usr/lib/wa2html/wa2html").is_file())
            self.assertEqual((root / "usr/bin/wa2html").readlink(), Path("../lib/wa2html/wa2html"))
            self.assertTrue((root / "usr/bin/wa2html").resolve().samefile(root / "usr/lib/wa2html/wa2html"))
            self.assertTrue((root / "usr/share/applications/wa2html.desktop").is_file())
            for size in linux.ICON_SIZES:
                icon = root / f"usr/share/icons/hicolor/{size}x{size}/apps/wa2html.png"
                self.assertTrue(icon.read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((root / "usr/share/doc/wa2html/LICENSE").is_file())
            self.assertEqual((root / "usr/lib/wa2html/wa2html").stat().st_mode & 0o777, 0o755)
            self.assertEqual((root / "usr/share/applications/wa2html.desktop").stat().st_mode & 0o777, 0o644)
            self.assertEqual(root.stat().st_mode & 0o777, 0o755)


class MacOS(unittest.TestCase):
    def test_iconset_has_every_size_iconutil_expects(self):
        self.assertEqual(len(macos.ICONSET), 10)
        self.assertEqual(macos.ICONSET["icon_512x512@2x.png"], 1024)
        self.assertEqual(macos.ICONSET["icon_16x16.png"], 16)

    def test_version_comes_from_the_package(self):
        self.assertEqual(linux.__version__, __version__)
        self.assertEqual(macos.__version__, __version__)


if __name__ == "__main__":
    unittest.main()
