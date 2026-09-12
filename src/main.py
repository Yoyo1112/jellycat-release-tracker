"""Entry point: fetch the catalogue, diff it against the last run, mail the news.

    python -m src.main              normal run (fetch, diff, mail, save snapshot)
    python -m src.main --seed       write a baseline snapshot, send nothing
    python -m src.main --dry-run    print events and dump the mail, send nothing
    python -m src.main --send-test  send a sample mail built from today's data
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile

from . import diff as diff_mod
from . import mailer, render, watchlist
from .fetch import STORES, FetchError, fetch_catalogue, price_label, product_url, store_of

SNAPSHOT_PATH = os.path.join("data", "snapshot.json")
EVENTS_PATH = os.path.join("data", "events.jsonl")

# A run that returns far fewer products than last time means something is wrong
# upstream, not that 20% of the shop closed.  Bail out rather than emit a few
# hundred bogus "delisted" events and overwrite a good snapshot with a bad one.
MIN_COUNT_RATIO = 0.8

COUNTDOWN_DAYS = 3


def _store_count(products: dict[str, dict], store_key: str) -> int:
    return sum(1 for product in products.values() if product.get("store") == store_key)


def load_snapshot(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_snapshot(path: str, products: dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": len(products),
        "products": products,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")


def append_events(path: str, events: list[dict]) -> None:
    if not events:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8") as handle:
        for event in events:
            handle.write(
                json.dumps(
                    {
                        "at": stamp,
                        "kind": event["kind"],
                        "store": event["product"].get("store", ""),
                        "name": event["product"].get("name", ""),
                        "url": product_url(event["product"]),
                        "price": event["product"].get("price", ""),
                        "status": event["product"].get("status", ""),
                        "badge": event["product"].get("badge", ""),
                        "starred": bool(event.get("starred")),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def print_events(events: list[dict], countdown: list[dict]) -> None:
    if countdown:
        print(f"\n⏰ 上架倒數（{COUNTDOWN_DAYS} 天內）")
        for row in countdown:
            star = "*" if row.get("starred") else " "
            print(f"  {star} D-{row['days']} {row['release']}  "
                  f"{store_of(row['product']).flag} {row['product'].get('name', '')}")

    if not events:
        print("\n沒有偵測到變化。")
        return

    print(f"\n偵測到 {len(events)} 筆事件：")
    current_kind = None
    for event in events:
        if event["kind"] != current_kind:
            current_kind = event["kind"]
            print(f"\n  [{diff_mod.KIND_LABELS[current_kind]}]")
        star = "*" if event.get("starred") else " "
        product = event["product"]
        print(f"    {star} {store_of(product).flag} {product.get('name', '')} "
              f"— {price_label(product)} "
              f"({product.get('badge') or product.get('status', '')})")


MANY_MATCHES = 20


def print_status(watched: list[dict], limit: int | None = None) -> None:
    if not watched:
        print("\n目前沒有命中任何商品。關鍵字可能拼錯，或這件商品不在目錄裡。")
        return

    print(f"\n⭐ 我的追蹤清單（{len(watched)} 筆）")
    if len(watched) >= MANY_MATCHES:
        print(f"   ⚠️  命中 {len(watched)} 件，關鍵字可能太寬鬆 —— 這些全部都會出現在每封信裡。")

    rows = sorted(watched, key=lambda p: (p.get("name", ""), p.get("store", "")))
    shown = rows[:limit] if limit else rows
    for product in shown:
        text, _colour = render.status_label(product)
        print(f"  {store_of(product).flag} {product.get('name', '')} — "
              f"{price_label(product)} · {text}")
        print(f"     {product_url(product)}")
    if limit and len(rows) > limit:
        print(f"   …另外還有 {len(rows) - limit} 筆")


def build_digest(events: list[dict], countdown: list[dict], total: int, watched: list[dict]):
    return (
        render.build_subject(events),
        render.render_text(events, countdown, total, watched),
        render.render_html(events, countdown, total, watched),
    )


def dump_preview(html_body: str) -> str:
    """Write the mail body out as a standalone page you can open in a browser.

    The mail itself is a bare fragment (EmailMessage declares UTF-8 for us);
    a local file needs its own charset or the Chinese renders as mojibake.
    """
    handle = tempfile.NamedTemporaryFile(
        prefix="jellycat-mail-", suffix=".html", delete=False, mode="w", encoding="utf-8"
    )
    handle.write('<!doctype html><meta charset="utf-8">\n' + html_body)
    handle.close()
    return handle.name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jellycat 上架追蹤器")
    parser.add_argument("--seed", action="store_true", help="只建立基準快照，不寄信")
    parser.add_argument("--dry-run", action="store_true", help="印出事件並輸出信件預覽，不寄信、不寫檔")
    parser.add_argument("--send-test", action="store_true", help="用當前目錄寄一封示範信")
    parser.add_argument("--status", action="store_true",
                        help="只印出追蹤清單目前狀態，不比對、不寄信、不寫檔")
    parser.add_argument("keywords", nargs="*", metavar="關鍵字",
                        help="搭配 --status 使用：改用這些關鍵字試算，不動 watchlist.txt")
    parser.add_argument("--always-send", action="store_true",
                        help="就算沒有變化也寄一封狀態回報（也可用 ALWAYS_SEND=1）")
    parser.add_argument("--snapshot", default=SNAPSHOT_PATH)
    parser.add_argument("--events", default=EVENTS_PATH)
    parser.add_argument("--watchlist", default=watchlist.DEFAULT_PATH)
    args = parser.parse_args(argv)

    if args.keywords and not args.status:
        parser.error("關鍵字只能搭配 --status 使用（試算用，不會寫進 watchlist.txt）")

    if args.keywords:
        rules = [keyword.strip().lower() for keyword in args.keywords if keyword.strip()]
        print(f"試算關鍵字（不會寫入 {args.watchlist}）：{rules}")
    else:
        rules = watchlist.load_rules(args.watchlist)
        print(f"追蹤清單：{len(rules)} 條規則" + (f" {rules}" if rules else "（空）"))

    try:
        current = fetch_catalogue()
    except FetchError as error:
        print(f"抓取失敗，這次不做任何變更：{error}", file=sys.stderr)
        return 1
    print(f"抓到 {len(current)} 件商品：" + "、".join(
        f"{store.flag} {store.label} {_store_count(current, store.key)}" for store in STORES
    ))

    watched = [product for product in current.values() if watchlist.matches(product, rules)]
    if rules and not watched:
        print("提醒：追蹤清單有規則，但目錄裡沒有任何商品命中。", file=sys.stderr)

    if args.status:
        print_status(watched, limit=MANY_MATCHES)
        return 0

    previous_snapshot = load_snapshot(args.snapshot)
    previous = (previous_snapshot or {}).get("products") or {}

    # Guard each store separately: a shortfall in one would otherwise be masked
    # by the other store's products in the total.
    for store in STORES:
        was = _store_count(previous, store.key)
        now = _store_count(current, store.key)
        if was and now < was * MIN_COUNT_RATIO:
            print(
                f"{store.label}商品數異常下滑（{was} → {now}），視為抓取異常；"
                "保留舊快照且不寄信。",
                file=sys.stderr,
            )
            return 1

    countdown = diff_mod.upcoming(current, COUNTDOWN_DAYS)
    for row in countdown:
        row["starred"] = watchlist.matches(row["product"], rules)
    countdown.sort(key=lambda row: (not row["starred"], row["days"], row["product"].get("name", "")))

    # --send-test pretends every Coming Soon item just launched, purely so the
    # mail path can be exercised without waiting for a real drop.
    if args.send_test:
        sample = []
        for store in STORES:
            rows = [
                (uid, product)
                for uid, product in current.items()
                if product.get("store") == store.key
            ][:3]
            for index, (uid, product) in enumerate(rows):
                kind = "launched" if index < 2 else "restock"
                sample.append({"kind": kind, "uid": uid, "product": product})
        for event in sample:
            event["starred"] = watchlist.matches(event["product"], rules)
        subject, text_body, html_body = build_digest(sample, countdown, len(current), watched)
        subject = "[測試] " + subject
        try:
            recipients = mailer.send(subject, text_body, html_body)
        except mailer.MailConfigError as error:
            print(error, file=sys.stderr)
            return 2
        print(f"測試信已寄出給 {len(recipients)} 位收件人：{', '.join(recipients)}")
        return 0

    if previous_snapshot is None and not args.dry_run:
        save_snapshot(args.snapshot, current)
        print(f"首次執行：已建立基準快照 {args.snapshot}，這次不寄信。")
        return 0

    if args.seed:
        save_snapshot(args.snapshot, current)
        print(f"已寫入基準快照 {args.snapshot}。")
        return 0

    events = diff_mod.diff(previous, current)
    for event in events:
        event["starred"] = watchlist.matches(event["product"], rules)

    # The noisy event kinds only go out for things you actually watch.
    events = [
        event
        for event in events
        if event["kind"] in diff_mod.SITE_WIDE_KINDS or event.get("starred")
    ]

    print_status(watched)
    print_events(events, countdown)

    if args.dry_run:
        subject, _text_body, html_body = build_digest(events, countdown, len(current), watched)
        preview = dump_preview(html_body)
        print(f"\n主旨：{subject}")
        print(f"信件預覽：{preview}")
        print("（--dry-run：未寄信、未寫入快照）")
        return 0

    always_send = args.always_send or os.environ.get("ALWAYS_SEND", "").strip() not in ("", "0")

    if events or (always_send and watched):
        subject, text_body, html_body = build_digest(events, countdown, len(current), watched)
        try:
            recipients = mailer.send(subject, text_body, html_body)
        except mailer.MailConfigError as error:
            print(f"寄信設定不完整，快照不更新以免漏掉這批事件：{error}", file=sys.stderr)
            return 2
        print(f"已寄出：{subject} → {len(recipients)} 位收件人")
        append_events(args.events, events)
    elif always_send:
        print("沒有變化，且追蹤清單是空的，不寄信。")
    else:
        print("沒有變化，不寄信。")

    save_snapshot(args.snapshot, current)
    print(f"快照已更新（{len(current)} 件）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
