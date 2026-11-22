"""Small JSON reader shared by the pptx scripts.

Windows editors and PowerShell redirection still emit UTF-16 with a BOM, and
PowerShell 5.1's UTF-8 output carries a BOM. A blueprint should not fail to load
because of the encoding its author's shell chose, so detect the BOM explicitly
and decode the common UTF-8/UTF-16 variants.
"""

from __future__ import annotations

import codecs
import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    """Read a JSON file written as UTF-8, UTF-8-BOM, or UTF-16 with a BOM."""
    raw = Path(path).read_bytes()
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        text = raw.decode("utf-16")
    elif raw.startswith(codecs.BOM_UTF8):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8")
    return json.loads(text)
