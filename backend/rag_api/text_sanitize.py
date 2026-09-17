"""NFC sanitization and U+FFFD repair for ingested legal text."""
from __future__ import annotations

import re
import unicodedata

_REPL = "\ufffd"
_REPL_BETWEEN_LETTERS = re.compile(r"(?<=[^\W\d_])\ufffd(?=[^\W\d_])")


def sanitize_text(s: str | None) -> str | None:
    """Normalize and repair replacement characters. None and empty pass through."""
    if not s:
        return s
    s = unicodedata.normalize("NFC", s)
    if _REPL in s:
        s = _REPL_BETWEEN_LETTERS.sub("'", s)
        s = s.replace(_REPL, "")
        s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[​‌‍﻿]", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() if s else s
