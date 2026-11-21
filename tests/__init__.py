"""Test package.

If the suite ever hangs (for example a window that cannot open on a CI
machine), print where every thread is stuck and stop instead of waiting for
the CI time limit. The whole suite normally runs in about 10 seconds.
"""

import faulthandler
import os
import sys

_LIMIT = int(os.environ.get("WA2HTML_TEST_TIMEOUT", "240"))
if _LIMIT > 0 and sys.stderr is not None:
    faulthandler.dump_traceback_later(_LIMIT, exit=True)
