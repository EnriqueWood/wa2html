"""Entry point of the Windows command-line executable.

Unlike the macOS and Linux programs, it never opens the window by itself:
Windows has a separate window-only executable for that.
"""

from wa2html.cli import main

raise SystemExit(main(allow_window=False))
