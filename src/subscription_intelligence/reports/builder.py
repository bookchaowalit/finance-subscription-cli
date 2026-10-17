"""Report builders for MVP CLI output."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def build_report(
    registry: dict[str, Any], *, within_days: int | None = None
) -> dict[str, Any]:
    subs = registry.get("subscriptions") or []
    today = date.today()
    window = within_days if within_days is not None else 90

    renewals = []
    for s in subs:
        rd = s.get("next_renewal_date")
        if not rd:
            continue
        try:
            d = date.fromisoformat(rd[:10])
        except ValueError:
            continue
        days_left = (d - today).days
        if 0 <= days_left <= window:
            renewals.append({**s, "days_until_renewal": days_left})
    renewals.sort(key=lambda x: x["days_until_renewal"])

    likely_unused = [
        s
        for s in subs
        if float(s.get("payment_evidence_score") or 0) >= 0.5
        and float(s.get("usage_evidence_score") or 0) < 0.25
    ]

    duplicates = [s for s in subs if s.get("duplicate_of")]

    by_rec: dict[str, list] = {}
    for s in subs:
        rec = s.get("recommendation") or "investigate"
        by_rec.setdefault(rec, []).append(s)

    monthly_total = sum(
        s.get("monthly_cost") or 0 for s in subs if s.get("monthly_cost")
    )
    annual_total = sum(s.get("annual_cost") or 0 for s in subs if s.get("annual_cost"))

    return {
        "scanned_at": registry.get("scanned_at"),
        "counts": {
            "subscriptions": len(subs),
            "renewals_within_window": len(renewals),
            "likely_unused": len(likely_unused),
            "duplicates": len(duplicates),
        },
        "totals": {
            "monthly_cost_estimate": round(monthly_total, 2),
            "annual_cost_estimate": round(annual_total, 2),
        },
        "upcoming_renewals": renewals,
        "likely_unused": likely_unused,
        "possible_duplicates": duplicates,
        "recommended_actions": by_rec,
        "draft_actions": registry.get("draft_actions") or [],
        "within_days": window,
    }


def format_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Subscription Intelligence Report")
    lines.append(f"Scanned at: {report.get('scanned_at') or 'never'}")
    totals = report.get("totals") or {}
    lines.append(
        f"Estimated spend: ~{totals.get('monthly_cost_estimate', 0)}/mo "
        f"(~{totals.get('annual_cost_estimate', 0)}/yr) across "
        f"{(report.get('counts') or {}).get('subscriptions', 0)} subscriptions"
    )
    lines.append("")

    lines.append(f"Upcoming renewals (within {report.get('within_days')}d)")
    renewals = report.get("upcoming_renewals") or []
    if not renewals:
        lines.append("- (none with estimated renewal date)")
    for s in renewals:
        amt = _fmt_amount(s)
        days = s.get("days_until_renewal")
        cycle = s.get("billing_cycle") or "unknown"
        lines.append(f"- {s['merchant']} — {amt} — {cycle} renews in {days} days")
    lines.append("")

    lines.append("Likely unused")
    unused = report.get("likely_unused") or []
    if not unused:
        lines.append("- (none flagged)")
    for s in unused:
        lines.append(
            f"- {s['merchant']} — paid evidence {s.get('payment_evidence_score')} "
            f"/ usage {s.get('usage_evidence_score')} — {_fmt_amount(s)}"
        )
    lines.append("")

    lines.append("Possible duplicates")
    dups = report.get("possible_duplicates") or []
    if not dups:
        lines.append("- (none flagged)")
    for s in dups:
        lines.append(f"- {s['merchant']} overlaps with {s.get('duplicate_of')}")
    lines.append("")

    lines.append("Recommended actions")
    actions = report.get("recommended_actions") or {}
    order = ["cancel", "downgrade", "investigate", "keep", "consider_subscribe"]
    any_action = False
    for key in order:
        for s in actions.get(key) or []:
            any_action = True
            lines.append(
                f"- {key.replace('_', ' ').title()}: {s['merchant']} — "
                f"{s.get('recommendation_reason') or ''}"
            )
    if not any_action:
        lines.append("- (run scan first)")
    lines.append("")

    drafts = report.get("draft_actions") or []
    if drafts:
        lines.append("Draft cancel/investigate checklist (human approval required)")
        for d in drafts:
            url = d.get("cancellation_url") or "no url captured"
            lines.append(
                f"- [{d.get('status')}] {d.get('action')} {d.get('merchant')} — {url}"
            )
        lines.append("")

    lines.append(
        "Worth layers: payment evidence (email) · usage evidence (calendar) · user value (manual)"
    )
    return "\n".join(lines)


def format_renewals_text(report: dict[str, Any]) -> str:
    lines = [f"Upcoming renewals (within {report.get('within_days')}d)", ""]
    renewals = report.get("upcoming_renewals") or []
    if not renewals:
        lines.append("(none)")
        return "\n".join(lines)
    for s in renewals:
        lines.append(
            f"- {s['merchant']} — {_fmt_amount(s)} — renews in {s.get('days_until_renewal')} days "
            f"({s.get('next_renewal_date')})"
        )
    return "\n".join(lines)


def _fmt_amount(s: dict[str, Any]) -> str:
    cur = s.get("currency") or ""
    monthly = s.get("monthly_cost")
    amount = s.get("amount")
    if monthly is not None:
        return f"{cur}{monthly}/mo"
    if amount is not None:
        return f"{cur}{amount}"
    return "amount unknown"
