"""
Recommendation engine — never auto-cancels.

Actions: keep | downgrade | cancel | investigate | consider_subscribe
Draft cancel/unsubscribe checklist only (status=draft).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Rough overlap groups for duplicate detection
OVERLAP_GROUPS: list[set[str]] = [
    {"openai", "chatgpt", "claude", "anthropic", "cursor", "kilo"},
    {"notion", "capacities", "craft"},
    {"todoist", "linear", "asana", "clickup"},
    {"1password", "lastpass", "bitwarden"},
    {"netflix", "crunchyroll", "disney", "hbo"},
    {"canva", "figma", "adobe"},
]


def apply_recommendations(registry: dict[str, Any]) -> dict[str, Any]:
    subs = registry.get("subscriptions", [])
    _mark_duplicates(subs)

    for sub in subs:
        rec, reason = _recommend(sub)
        sub["recommendation"] = rec
        sub["recommendation_reason"] = reason

    registry["draft_actions"] = build_draft_actions(registry)
    return registry


def build_draft_actions(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Human-approved checklist only — never executed against Gmail."""
    existing = {
        (d.get("subscription_id"), d.get("action")): d
        for d in registry.get("draft_actions") or []
        if d.get("status") in {"approved", "done", "rejected"}
    }
    drafts: list[dict[str, Any]] = []
    for sub in registry.get("subscriptions", []):
        rec = sub.get("recommendation")
        if rec not in {"cancel", "investigate", "downgrade"}:
            continue
        action = "cancel" if rec == "cancel" else rec
        key = (sub["id"], action)
        if key in existing:
            drafts.append(existing[key])
            continue
        drafts.append(
            {
                "action": action if action != "cancel" else "cancel",
                "subscription_id": sub["id"],
                "merchant": sub["merchant"],
                "status": "draft",
                "cancellation_url": sub.get("cancellation_url"),
                "notes": sub.get("recommendation_reason") or "",
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return drafts


def _recommend(sub: dict[str, Any]) -> tuple[str, str]:
    pay = float(sub.get("payment_evidence_score") or 0)
    use = float(sub.get("usage_evidence_score") or 0)
    user_val = sub.get("user_value")
    amount = sub.get("monthly_cost")
    status = sub.get("status")

    if pay < 0.35:
        return "investigate", "Payment found is weak or plan unclear"

    if user_val is not None:
        if user_val <= 2 and pay >= 0.5:
            return "cancel", f"User value {user_val}/5 with confirmed payment"
        if user_val >= 4:
            return "keep", f"User value {user_val}/5"
        if user_val == 3 and amount and amount >= 15 and use < 0.4:
            return "downgrade", "Medium value, high cost, low usage evidence"

    if use >= 0.6 and pay >= 0.5:
        return "keep", "Used frequently with payment evidence"
    if use < 0.2 and pay >= 0.55:
        cost_bit = f" (~{sub.get('currency') or ''}{amount}/mo)" if amount else ""
        return "cancel", f"Low usage / paid subscription{cost_bit}"
    if use < 0.4 and amount and amount >= 20:
        return "downgrade", "Moderate usage and relatively high monthly cost"
    if status == "trial":
        return "investigate", "Trial signal — decide before conversion"
    if sub.get("duplicate_of"):
        return "investigate", f"Possible duplicate of {sub['duplicate_of']}"

    if pay >= 0.5 and use >= 0.35:
        return "keep", "Payment and some usage evidence"
    return "investigate", "Need more signal (amount, cycle, or usage)"


def _mark_duplicates(subs: list[dict[str, Any]]) -> None:
    by_id = {s["normalized_name"]: s for s in subs}
    for group in OVERLAP_GROUPS:
        present = [s for s in subs if s["normalized_name"] in group or s["id"] in group]
        # also match if normalized name is in group
        present = [s for s in subs if any(g in s["normalized_name"] for g in group)]
        if len(present) < 2:
            continue
        # cheapest or highest usage as primary
        present_sorted = sorted(
            present,
            key=lambda s: (
                -(float(s.get("usage_evidence_score") or 0)),
                float(s.get("monthly_cost") or 9999),
            ),
        )
        primary = present_sorted[0]
        for other in present_sorted[1:]:
            other["duplicate_of"] = primary["id"]
