"""Print the last lines of a log as a GitHub Actions error annotation.

Annotations of public repositories can be read through the API without
signing in, so a failing job explains itself to anyone looking at it.
Usage: python .github/scripts/annotate_tail.py FILE [LINES]
"""

import sys
from pathlib import Path

path = Path(sys.argv[1])
count = int(sys.argv[2]) if len(sys.argv) > 2 else 45
if path.exists():
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
else:
    lines = [f"({path} was not written)"]
text = "\n".join(lines).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
print(f"::error title=End of the test output::{text}")
