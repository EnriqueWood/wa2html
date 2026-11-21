"""Entry point of the Windows window-only executable (built with --windowed).

Double-clicked it opens the window; a file dropped on it is preselected.
"""

from wa2html.gui import main

raise SystemExit(main())
