"""scripts/ を import path に載せる(スクリプト群はパッケージではなくフラットな module 群)。

実行: リポジトリルートで `python -m unittest discover -s tests -t .`
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
