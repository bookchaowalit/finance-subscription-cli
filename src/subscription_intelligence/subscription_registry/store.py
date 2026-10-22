"""Local subscription registry (JSON under product data/)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..extractors.signals import ExtractedSignal
from ..paths import REGISTRY_PATH, ensure_data_dirs


def empty_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "scanned_at": None,
        "scan_days": None,
        "source": {
            "gmail_messages_scanned": 0,
            "signals_extracted": 0,
            "calendar_events_scanned": 0,
        },
        "subscriptions": [],
        "draft_actions": [],
    }


class RegistryStore:
    def __init__(self, path: Path | None = None):
        self.path = path or REGISTRY_PATH
        ensure_data_dirs()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_registry()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("subscriptions", [])
        data.setdefault("draft_actions", [])
        data.setdefault("source", empty_registry()["source"])
        return data

    def save(self, registry: dict[str, Any]) -> Path:
        ensure_data_dirs()
        self.path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return self.path

    def merge_signals(
        self,
        signals: list[ExtractedSignal],
        *,
        gmail_scanned: int = 0,
        calendar_scanned: int = 0,
        scan_days: int | None = None,
        usage_by_merchant: dict[str, list[str]] | None = None,
        preserve_user_value: bool = True,
    ) -> dict[str, Any]:
        """Merge extracted signals into subscriptions keyed by normalized_name."""
        reg = self.load()
        existing = {s["normalized_name"]: s for s in reg.get("subscriptions", [])}
        usage_by_merchant = usage_by_merchant or {}

        for sig in signals:
            key = sig.normalized_name
            sub = existing.get(key)
            if not sub:
                sub = {
                    "id": key,
                    "merchant": sig.merchant,
                    "normalized_name": key,
                    "amount": None,
                    "currency": None,
                    "billing_cycle": "unknown",
                    "monthly_cost": None,
                    "annual_cost": None,
                    "next_renewal_date": None,
                    "last_payment_date": None,
                    "status": "unknown",
                    "payment_evidence_score": 0.0,
                    "usage_evidence_score": 0.0,
                    "user_value": None,
                    "recommendation": None,
                    "recommendation_reason": None,
                    "cancellation_url": None,
                    "source_message_ids": [],
                    "evidence": [],
                    "usage_signals": [],
                    "duplicate_of": None,
                    "updated_at": _now(),
                }
                existing[key] = sub
            elif preserve_user_value:
                # keep user_value from previous load
                pass

            if sig.source_message_id not in sub["source_message_ids"]:
                sub["source_message_ids"].append(sig.source_message_id)

            # Dedup evidence by message id + event type
            ev_key = (sig.source_message_id, sig.event_type)
            have = {(e.get("source_message_id"), e.get("event_type")) for e in sub["evidence"]}
            if ev_key not in have:
                sub["evidence"].append(sig.to_evidence_dict())

            if sig.amount is not None:
                sub["amount"] = sig.amount
                sub["currency"] = sig.currency or sub.get("currency")
            if sig.billing_cycle:
                sub["billing_cycle"] = sig.billing_cycle
            if sig.event_date and sig.event_type in {
                "invoice",
                "receipt",
                "renewal",
                "payment",
            }:
                prev = sub.get("last_payment_date")
                if not prev or sig.event_date > prev:
                    sub["last_payment_date"] = sig.event_date
            if sig.cancellation_url:
                sub["cancellation_url"] = sig.cancellation_url
            if sig.event_type == "trial":
                sub["status"] = "trial"
            elif sig.event_type in {"invoice", "receipt", "renewal", "payment"} and (
                sub.get("status") != "cancelled"
            ):
                sub["status"] = "active"

            sub["updated_at"] = _now()

        # Attach usage signals + cost rollups
        for sub in existing.values():
            hits = usage_by_merchant.get(sub["merchant"], []) + usage_by_merchant.get(
                sub["normalized_name"], []
            )
            # also try case-insensitive merchant keys
            for k, v in usage_by_merchant.items():
                if k.lower() == sub["merchant"].lower() or k.lower() == sub["normalized_name"]:
                    hits.extend(v)
            if hits:
                sub["usage_signals"] = list(dict.fromkeys(sub.get("usage_signals", []) + hits))[:20]
            _rollup_costs(sub)
            _estimate_renewal(sub)

        reg["subscriptions"] = sorted(
            existing.values(),
            key=lambda s: (
                s.get("monthly_cost") is None,
                -(s.get("monthly_cost") or 0),
                s["merchant"],
            ),
        )
        reg["scanned_at"] = _now()
        reg["scan_days"] = scan_days
        reg["source"] = {
            "gmail_messages_scanned": gmail_scanned,
            "signals_extracted": len(signals),
            "calendar_events_scanned": calendar_scanned,
        }
        return reg


def _rollup_costs(sub: dict[str, Any]) -> None:
    amount = sub.get("amount")
    if amount is None:
        sub["monthly_cost"] = None
        sub["annual_cost"] = None
        return
    cycle = sub.get("billing_cycle") or "unknown"
    if cycle == "annual":
        sub["annual_cost"] = amount
        sub["monthly_cost"] = round(amount / 12, 2)
    elif cycle == "weekly":
        sub["monthly_cost"] = round(amount * 4.33, 2)
        sub["annual_cost"] = round(amount * 52, 2)
    elif cycle == "monthly":
        sub["monthly_cost"] = amount
        sub["annual_cost"] = round(amount * 12, 2)
    else:
        # unknown: treat as monthly if amount < 200 else annual-ish heuristic
        if amount >= 200:
            sub["billing_cycle"] = "annual"
            sub["annual_cost"] = amount
            sub["monthly_cost"] = round(amount / 12, 2)
        else:
            sub["billing_cycle"] = "monthly"
            sub["monthly_cost"] = amount
            sub["annual_cost"] = round(amount * 12, 2)


def _estimate_renewal(sub: dict[str, Any]) -> None:
    last = sub.get("last_payment_date")
    if not last:
        return
    try:
        d = date.fromisoformat(last[:10])
    except ValueError:
        return
    cycle = sub.get("billing_cycle") or "monthly"
    if cycle == "annual":
        nxt = _add_year(d)
    elif cycle == "weekly":
        from datetime import timedelta

        nxt = d + timedelta(days=7)
    else:
        # monthly
        month = d.month + 1
        year = d.year + (1 if month > 12 else 0)
        month = month if month <= 12 else 1
        day = min(d.day, 28)
        nxt = date(year, month, day)
    # if estimated renewal already past, roll forward once more
    today = date.today()
    if nxt < today:
        if cycle == "annual":
            nxt = _add_year(nxt)
        else:
            month = nxt.month + 1
            year = nxt.year + (1 if month > 12 else 0)
            month = month if month <= 12 else 1
            nxt = date(year, month, min(nxt.day, 28))
    sub["next_renewal_date"] = nxt.isoformat()


def _add_year(d: date) -> date:
    """Same day next year; 29 Feb falls back to 28 Feb."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
