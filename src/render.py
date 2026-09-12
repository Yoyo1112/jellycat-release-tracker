"""Render the notification mail: a Chinese HTML digest plus a plain-text twin.

Mail clients are a hostile rendering target, so everything here is tables and
inline styles -- no <style> block, no flexbox, no external CSS.  Product
thumbnails are hotlinked straight from the BigCommerce CDN; Gmail proxies and
caches them.
"""

from __future__ import annotations

import datetime as dt
import html
import zoneinfo

from .diff import KIND_LABELS, SITE_WIDE_KINDS, WATCHLIST_ONLY_KINDS
from .fetch import price_label, product_url, store_of

TAIPEI = zoneinfo.ZoneInfo("Asia/Taipei")

SECTION_ICONS = {
    "launched": "🎉",
    "new_product": "✨",
    "coming_soon_added": "📣",
    "release_date_set": "📅",
    "restock": "📦",
    "sold_out": "🚫",
    "price_change": "💷",
    "delisted": "👋",
}

INK = "#2b2b2b"
MUTED = "#7a7a7a"
LINE = "#e8e4de"
PAPER = "#faf8f5"
ACCENT = "#c4553b"


def _now() -> dt.datetime:
    return dt.datetime.now(TAIPEI)


def _price(product: dict) -> str:
    return price_label(product)


def _flag(product: dict) -> str:
    """Storefront marker, so a UK and a US row are never confused."""
    return store_of(product).flag


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


# --------------------------------------------------------------------------- #
# subject
# --------------------------------------------------------------------------- #

def build_subject(events: list[dict]) -> str:
    counts: dict[str, int] = {}
    for event in events:
        counts[event["kind"]] = counts.get(event["kind"], 0) + 1

    starred = sum(1 for event in events if event.get("starred"))

    parts = []
    for kind in SITE_WIDE_KINDS + WATCHLIST_ONLY_KINDS:
        if counts.get(kind):
            parts.append(f"{counts[kind]} 件{KIND_LABELS[kind]}")
        if len(parts) == 2:
            break

    headline = "、".join(parts) if parts else "目錄有更新"
    star = "⭐ " if starred else ""
    return f"{star}🧸 Jellycat：{headline}"


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

def _card_html(event: dict) -> str:
    product = event["product"]
    url = product_url(product)
    star = "⭐ " if event.get("starred") else ""

    notes = []
    symbol = store_of(product).symbol
    if event["kind"] == "price_change":
        notes.append(
            f"{symbol}{_esc(event.get('was', ''))} → {symbol}{_esc(product.get('price', ''))}"
        )
    elif event["kind"] == "release_date_set":
        was = event.get("was") or "（原本沒有日期）"
        notes.append(f"{_esc(was)} → {_esc(product.get('badge', ''))}")
    elif product.get("badge"):
        notes.append(_esc(product["badge"]))

    if event["kind"] in ("launched", "new_product", "restock"):
        notes.append("有貨" if product.get("in_stock") else "目前缺貨")

    note_html = (
        f'<div style="margin-top:4px;font-size:12px;color:{MUTED};">'
        f'{" · ".join(notes)}</div>'
        if notes
        else ""
    )

    image = product.get("image")
    image_cell = (
        f'<td width="72" valign="top" style="padding-right:12px;">'
        f'<a href="{_esc(url)}"><img src="{_esc(image)}" width="72" height="72" alt="" '
        f'style="display:block;width:72px;height:72px;border-radius:8px;'
        f'border:1px solid {LINE};object-fit:cover;"></a></td>'
        if image
        else ""
    )

    return f"""
      <tr><td style="padding:10px 0;border-bottom:1px solid {LINE};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          {image_cell}
          <td valign="top">
            <a href="{_esc(url)}" style="color:{INK};font-size:15px;font-weight:600;
               text-decoration:none;line-height:1.35;">{star}{_flag(product)} {_esc(product.get("name", ""))}</a>
            <div style="margin-top:3px;font-size:14px;color:{ACCENT};font-weight:600;">
              {_price(product)}</div>
            {note_html}
          </td>
        </tr></table>
      </td></tr>"""


def _section_html(kind: str, events: list[dict]) -> str:
    if not events:
        return ""

    icon = SECTION_ICONS.get(kind, "•")
    rows = "".join(_card_html(event) for event in events)
    return f"""
    <tr><td style="padding:22px 0 4px;">
      <div style="font-size:16px;font-weight:700;color:{INK};">
        {icon} {KIND_LABELS[kind]} <span style="color:{MUTED};font-weight:400;">
        ({len(events)})</span></div>
    </td></tr>
    <tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0">{rows}</table></td></tr>"""


def _countdown_html(rows: list[dict]) -> str:
    if not rows:
        return ""

    items = []
    for row in rows:
        product = row["product"]
        star = "⭐ " if row.get("starred") else ""
        label = "今天上架！" if row["days"] == 0 else f"還有 {row['days']} 天"
        items.append(
            f'<tr><td style="padding:6px 0;border-bottom:1px solid {LINE};">'
            f'<a href="{_esc(product_url(product))}" style="color:{INK};font-size:14px;'
            f'font-weight:600;text-decoration:none;">{star}{_flag(product)} '
            f'{_esc(product.get("name", ""))}</a>'
            f'<span style="color:{MUTED};font-size:13px;"> — {_price(product)}</span>'
            f'<div style="font-size:12px;color:{ACCENT};font-weight:600;margin-top:2px;">'
            f'{row["release"].strftime("%m/%d")} · {label}</div></td></tr>'
        )

    return f"""
    <tr><td style="padding:22px 0 4px;">
      <div style="font-size:16px;font-weight:700;color:{INK};">⏰ 上架倒數</div>
    </td></tr>
    <tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      border="0">{"".join(items)}</table></td></tr>"""


def render_html(events: list[dict], countdown: list[dict], total: int) -> str:
    grouped = {kind: [] for kind in SITE_WIDE_KINDS + WATCHLIST_ONLY_KINDS}
    for event in events:
        grouped[event["kind"]].append(event)

    # Watchlist hits float to the top of their section.
    for bucket in grouped.values():
        bucket.sort(key=lambda event: (not event.get("starred"), event["product"].get("name", "")))

    sections = "".join(
        _section_html(kind, grouped[kind])
        for kind in SITE_WIDE_KINDS + WATCHLIST_ONLY_KINDS
    )
    stamp = _now().strftime("%Y/%m/%d %H:%M")

    return f"""<div style="margin:0;padding:0;background:{PAPER};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:{PAPER};padding:20px 12px;">
<tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
    style="max-width:560px;background:#ffffff;border:1px solid {LINE};border-radius:14px;
    padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans TC',
    'PingFang TC','Microsoft JhengHei',Helvetica,Arial,sans-serif;">

    <tr><td style="padding-bottom:6px;">
      <div style="font-size:20px;font-weight:800;color:{INK};">🧸 Jellycat 上架追蹤</div>
      <div style="font-size:12px;color:{MUTED};margin-top:4px;">
        {stamp}（台北時間） · 本次掃描 {total} 件商品<br>
        🇬🇧 jellycat.com（英鎊）　🇺🇸 us.jellycat.com（美元）</div>
    </td></tr>

    {_countdown_html(countdown)}
    {sections}

    <tr><td style="padding-top:24px;border-top:1px solid {LINE};">
      <div style="font-size:11px;color:{MUTED};line-height:1.6;">
        資料來自 jellycat.com 公開商品目錄，僅在偵測到變化時寄信。<br>
        ⭐ 代表命中你的追蹤清單（watchlist.txt）。同一件商品在兩站是分開追蹤的。
      </div>
    </td></tr>

  </table>
</td></tr></table></div>"""


# --------------------------------------------------------------------------- #
# plain text
# --------------------------------------------------------------------------- #

def render_text(events: list[dict], countdown: list[dict], total: int) -> str:
    lines = [
        "🧸 Jellycat 上架追蹤",
        f"{_now().strftime('%Y/%m/%d %H:%M')}（台北時間） · 本次掃描 {total} 件",
        "🇬🇧 jellycat.com（英鎊）  🇺🇸 us.jellycat.com（美元）",
    ]

    if countdown:
        lines += ["", "⏰ 上架倒數"]
        for row in countdown:
            star = "⭐ " if row.get("starred") else ""
            label = "今天上架！" if row["days"] == 0 else f"還有 {row['days']} 天"
            lines.append(
                f"  {star}{_flag(row['product'])} {row['product'].get('name', '')}"
                f" — {_price(row['product'])} · {row['release'].strftime('%m/%d')} {label}"
            )
            lines.append(f"    {product_url(row['product'])}")

    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event["kind"], []).append(event)

    for kind in SITE_WIDE_KINDS + WATCHLIST_ONLY_KINDS:
        bucket = grouped.get(kind)
        if not bucket:
            continue
        lines += ["", f"{SECTION_ICONS.get(kind, '•')} {KIND_LABELS[kind]} ({len(bucket)})"]
        for event in sorted(bucket, key=lambda e: (not e.get("starred"), e["product"].get("name", ""))):
            product = event["product"]
            star = "⭐ " if event.get("starred") else ""
            extra = ""
            if kind == "price_change":
                symbol = store_of(product).symbol
                extra = f" · {symbol}{event.get('was', '')} → {symbol}{product.get('price', '')}"
            elif product.get("badge"):
                extra = f" · {product['badge']}"
            lines.append(
                f"  {star}{_flag(product)} {product.get('name', '')} — {_price(product)}{extra}"
            )
            lines.append(f"    {product_url(product)}")

    lines += ["", "⭐ 代表命中 watchlist.txt 的追蹤清單。"]
    return "\n".join(lines)
