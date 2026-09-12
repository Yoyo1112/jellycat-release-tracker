"""Turn two catalogue snapshots into a list of notable events.

Site-wide events (everyone hears about these):

    launched              Coming Soon -> Live.  The headline event.
    new_product           a uid we have never seen before
    coming_soon_added     a new Coming Soon listing, i.e. an announced release
    release_date_set      the badge gained or changed a concrete release date
    restock               a Live product went out of stock -> in stock

Watchlist-only events (suppressed for everything else, because ~250 products
are out of stock at any moment and the mail would be unreadable):

    sold_out              in stock -> out of stock
    price_change          the price moved
    delisted              the product vanished from the catalogue
"""

from __future__ import annotations

import datetime as dt
import re

COMING_SOON = "Coming Soon"

SITE_WIDE_KINDS = (
    "launched",
    "new_product",
    "coming_soon_added",
    "release_date_set",
    "restock",
)
WATCHLIST_ONLY_KINDS = ("sold_out", "price_change", "delisted")

# Ordering used for both the mail sections and the console output.
KIND_ORDER = SITE_WIDE_KINDS + WATCHLIST_ONLY_KINDS

KIND_LABELS = {
    "launched": "正式上架",
    "new_product": "全新商品",
    "coming_soon_added": "新公告：即將上架",
    "release_date_set": "上架日期公布／異動",
    "restock": "補貨到",
    "sold_out": "售罄",
    "price_change": "價格變動",
    "delisted": "已下架",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# e.g. "Available 16th September", "Available 1st October"
_RELEASE_BADGE = re.compile(
    r"available\s+(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)", re.IGNORECASE
)


def parse_release_date(badge: str, today: dt.date | None = None) -> dt.date | None:
    """Read a release date out of a badge like "Available 16th September".

    The badge carries no year, so we assume the nearest sensible one: a date
    more than a month in the past is read as next year's.
    """
    if not badge:
        return None

    match = _RELEASE_BADGE.search(badge)
    if not match:
        return None

    month = MONTHS.get(match.group(2).lower())
    if not month:
        return None

    today = today or dt.date.today()
    day = int(match.group(1))
    for year in (today.year, today.year + 1):
        try:
            candidate = dt.date(year, month, day)
        except ValueError:
            return None
        if (candidate - today).days >= -31:
            return candidate
    return None


def _event(kind: str, uid: str, product: dict, **extra) -> dict:
    event = {"kind": kind, "uid": uid, "product": product}
    event.update(extra)
    return event


def diff(previous: dict[str, dict], current: dict[str, dict]) -> list[dict]:
    """Compare two `{uid: product}` maps and return the events between them."""
    events: list[dict] = []

    for uid, now in current.items():
        before = previous.get(uid)

        if before is None:
            if now.get("status") == COMING_SOON:
                events.append(_event("coming_soon_added", uid, now))
            else:
                events.append(_event("new_product", uid, now))
            continue

        was_coming_soon = before.get("status") == COMING_SOON
        is_coming_soon = now.get("status") == COMING_SOON
        status_changed = was_coming_soon != is_coming_soon

        if was_coming_soon and not is_coming_soon:
            events.append(_event("launched", uid, now, was=before.get("status")))
        elif not was_coming_soon and is_coming_soon:
            events.append(_event("coming_soon_added", uid, now))
        elif is_coming_soon and before.get("badge") != now.get("badge"):
            # Only interesting while the product is still unreleased: a date got
            # pinned down, or moved.
            if parse_release_date(now.get("badge", "")):
                events.append(
                    _event("release_date_set", uid, now, was=before.get("badge", ""))
                )

        # A launch already says whether the thing is buyable, so don't also
        # report it as a restock -- one product, one headline.
        if not status_changed:
            if not before.get("in_stock") and now.get("in_stock") and not is_coming_soon:
                events.append(_event("restock", uid, now))
            elif before.get("in_stock") and not now.get("in_stock"):
                events.append(_event("sold_out", uid, now))

        if before.get("price") != now.get("price") and before.get("price") and now.get("price"):
            events.append(_event("price_change", uid, now, was=before.get("price")))

    for uid, gone in previous.items():
        if uid not in current:
            events.append(_event("delisted", uid, gone))

    events.sort(key=lambda event: (KIND_ORDER.index(event["kind"]), event["product"].get("name", "")))
    return events


def upcoming(current: dict[str, dict], within_days: int = 3, today: dt.date | None = None) -> list[dict]:
    """Coming Soon products whose announced release date is `within_days` away."""
    today = today or dt.date.today()
    rows = []

    for uid, product in current.items():
        if product.get("status") != COMING_SOON:
            continue
        release = parse_release_date(product.get("badge", ""), today)
        if release is None:
            continue
        days = (release - today).days
        if 0 <= days <= within_days:
            rows.append({"uid": uid, "product": product, "release": release, "days": days})

    rows.sort(key=lambda row: (row["days"], row["product"].get("name", "")))
    return rows
