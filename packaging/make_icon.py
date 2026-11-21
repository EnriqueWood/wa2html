"""Write the Windows icon used by the executables: python packaging/make_icon.py OUT.ico"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wa2html.icon import ico  # noqa: E402

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(ico())
print(f"wrote {out} ({out.stat().st_size:,} bytes)")
