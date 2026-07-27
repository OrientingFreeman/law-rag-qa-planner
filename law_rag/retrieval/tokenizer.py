from __future__ import annotations

import re
from collections import Counter

TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def char_ngrams(text: str, n: int = 2) -> Counter[str]:
    normalized = "".join(tokenize(text))
    if len(normalized) < n:
        return Counter([normalized]) if normalized else Counter()
    return Counter(normalized[i : i + n] for i in range(len(normalized) - n + 1))
