"""Match catalogue products against the user-maintained watchlist.

watchlist.txt holds one rule per line.  A rule is a case-insensitive substring
matched against the product's name, SKU and slug; blank lines and lines starting
with '#' are ignored.  An empty watchlist means "nothing is specifically
watched" -- site-wide events still go out, but the watchlist-only events
(sold out, price change, delisted) are suppressed.
"""

from __future__ import annotations

import os

DEFAULT_PATH = "watchlist.txt"


def load_rules(path: str = DEFAULT_PATH) -> list[str]:
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    rules = []
    for line in lines:
        rule = line.split("#", 1)[0].strip().lower()
        if rule:
            rules.append(rule)
    return rules


def matches(product: dict, rules: list[str]) -> bool:
    if not rules:
        return False

    haystack = " ".join(
        [product.get("name", ""), product.get("sku", ""), product.get("url", "")]
    ).lower()
    return any(rule in haystack for rule in rules)
