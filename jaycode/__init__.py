from __future__ import annotations

import sys
from pathlib import Path


_SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

__path__ = [str(_SOURCE_ROOT / "jaycode")]
