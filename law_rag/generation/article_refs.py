from __future__ import annotations

import re

# Korean statute article forms:
#   제28조, 제28조의8 (canonical)
# Also accepts the uncommon legacy form 제28의8조 for backward compatibility.
ARTICLE_PATTERN = re.compile(
    r"제\s*\d+\s*조(?:\s*의\s*\d+)?|제\s*\d+(?:\s*의\s*\d+)?\s*조"
)


def normalize_article_ref(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    legacy = re.fullmatch(r"제(\d+)의(\d+)조", compact)
    if legacy:
        return f"제{legacy.group(1)}조의{legacy.group(2)}"
    return compact


def extract_article_refs(text: str) -> list[str]:
    return [normalize_article_ref(match.group(0)) for match in ARTICLE_PATTERN.finditer(text)]
