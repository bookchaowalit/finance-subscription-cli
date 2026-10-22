"""
subscription-intel CLI

  scan --days 365
  report [--json]
  renewals --within 90d
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Ensure package root on path when run as script
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from subscription_intelligence.calendar_adapter import CalendarReadOnlyAdapter
from subscription_intelligence.extractors import extract_signals_from_message
from subscription_intelligence.gmail_adapter import GmailReadOnlyAdapter
from subscription_intelligence.paths import REPORTS_DIR, ensure_data_dirs
from subscription_intelligence.recommendations import apply_recommendations
from subscription_intelligence.reports.builder import (
    build_report,
    format_renewals_text,
    format_report_text,
)
from subscription_intelligence.scoring import apply_scores
from subscription_intelligence.subscription_registry import RegistryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="subscription-intel",
        description="Subscription Intelligence — read-only Gmail/Calendar MVP",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan Gmail (+ Calendar) and update registry")
    p_scan.add_argument("--days", type=int, default=365, help="Lookback days (default 365)")
    p_scan.add_argument("--max", type=int, default=200, help="Max Gmail messages to fetch")
    p_scan.add_argument("--no-calendar", action="store_true", help="Skip calendar usage signals")
    p_scan.add_argument(
        "--fresh",
        action="store_true",
        help="Replace registry subscriptions (keeps draft actions with approved/done/rejected)",
    )
    p_scan.add_argument("--json", action="store_true", help="JSON summary")

    p_report = sub.add_parser("report", help="Print full intelligence report")
    p_report.add_argument("--within", default="90d", help="Renewal window e.g. 90d")
    p_report.add_argument("--json", action="store_true")

    p_ren = sub.add_parser("renewals", help="Upcoming renewals only")
    p_ren.add_argument("--within", default="90d", help="Window e.g. 90d")
    p_ren.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "renewals":
        return cmd_renewals(args)
    return 1


def cmd_scan(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    print(f"🔍 Scanning Gmail (read-only) last {args.days} days…")
    gmail = GmailReadOnlyAdapter()
    try:
        profile = gmail.profile()
        print(f"   Account: {profile.get('emailAddress')}")
    except Exception as e:  # noqa: BLE001 - CLI auth check reports any failure to the user
        print(f"❌ Gmail auth failed: {e}", file=sys.stderr)
        print(
            "   Re-auth: refresh GOOGLE_REFRESH_TOKEN in your secret manager",
            file=sys.stderr,
        )
        return 1

    messages = gmail.fetch_subscription_candidates(days=args.days, max_results=args.max)
    print(f"   Messages matched query: {len(messages)}")

    signals = []
    for msg in messages:
        signals.extend(extract_signals_from_message(msg))
    print(f"   Signals extracted: {len(signals)}")

    usage_by_merchant: dict[str, list[str]] = {}
    cal_count = 0
    if not args.no_calendar:
        print("📅 Scanning Calendar for usage evidence…")
        cal = CalendarReadOnlyAdapter(token=gmail.token)
        events = cal.list_events(days_back=min(args.days, 180), days_forward=30)
        cal_count = len(events)
        merchants = {s.merchant for s in signals}
        for m in merchants:
            hits = cal.usage_hits_for_merchant(m, events)
            if hits:
                usage_by_merchant[m] = hits
        print(f"   Calendar events scanned: {cal_count}")

    store = RegistryStore()
    if args.fresh and store.path.exists():
        prev = store.load()
        kept_drafts = [
            d
            for d in (prev.get("draft_actions") or [])
            if d.get("status") in {"approved", "done", "rejected"}
        ]
        from subscription_intelligence.subscription_registry.store import empty_registry

        blank = empty_registry()
        blank["draft_actions"] = kept_drafts
        store.save(blank)
        print("   Fresh registry (prior approved drafts kept)")

    reg = store.merge_signals(
        signals,
        gmail_scanned=len(messages),
        calendar_scanned=cal_count,
        scan_days=args.days,
        usage_by_merchant=usage_by_merchant,
    )
    reg = apply_scores(reg)
    reg = apply_recommendations(reg)
    path = store.save(reg)

    summary = {
        "status": "ok",
        "registry_path": str(path),
        "gmail_messages_scanned": len(messages),
        "signals_extracted": len(signals),
        "subscriptions": len(reg.get("subscriptions") or []),
        "calendar_events_scanned": cal_count,
        "draft_actions": len(reg.get("draft_actions") or []),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"✅ Registry updated: {path}")
        print(
            f"   Subscriptions: {summary['subscriptions']} | "
            f"Draft actions: {summary['draft_actions']}"
        )
        print("   Next: subscription-intel report")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = RegistryStore()
    reg = store.load()
    if not reg.get("subscriptions"):
        print("Registry empty. Run: subscription-intel scan --days 365", file=sys.stderr)
        return 1
    within = _parse_within(args.within)
    report = build_report(reg, within_days=within)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        text = format_report_text(report)
        print(text)
        ensure_data_dirs()
        out = REPORTS_DIR / "latest-report.txt"
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\n(saved {out})")
    return 0


def cmd_renewals(args: argparse.Namespace) -> int:
    store = RegistryStore()
    reg = store.load()
    if not reg.get("subscriptions"):
        print("Registry empty. Run: subscription-intel scan --days 365", file=sys.stderr)
        return 1
    within = _parse_within(args.within)
    report = build_report(reg, within_days=within)
    if args.json:
        print(json.dumps(report.get("upcoming_renewals") or [], indent=2, ensure_ascii=False))
    else:
        print(format_renewals_text(report))
    return 0


def _parse_within(raw: str) -> int:
    raw = (raw or "90d").strip().lower()
    m = re.match(r"^(\d+)\s*d(ays?)?$", raw)
    if m:
        return int(m.group(1))
    if raw.isdigit():
        return int(raw)
    raise SystemExit(f"Invalid --within value: {raw} (use e.g. 90d)")


if __name__ == "__main__":
    raise SystemExit(main())
