"""Registry merge, cost roll-up and renewal estimation (offline, temp files only)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from subscription_intelligence.extractors.signals import ExtractedSignal
from subscription_intelligence.subscription_registry.store import (
    RegistryStore,
    _estimate_renewal,
    _rollup_costs,
)


def _sig(**kw: Any) -> ExtractedSignal:
    base: dict[str, Any] = {
        "merchant": "Notion",
        "normalized_name": "notion",
        "event_type": "invoice",
        "amount": 10.0,
        "currency": "USD",
        "billing_cycle": "monthly",
        "event_date": "2026-07-01",
        "source_message_id": "m1",
        "confidence": 0.8,
        "snippet_evidence": "Thanks for your payment",
        "cancellation_url": None,
        "from_address": "billing@notion.so",
        "subject": "Your Notion invoice",
    }
    base.update(kw)
    return ExtractedSignal(**base)


def test_merge_dedups_evidence_and_keeps_latest_payment(tmp_path: Path) -> None:
    store = RegistryStore(path=tmp_path / "registry.json")
    reg = store.merge_signals(
        [
            _sig(),
            _sig(),  # same message + event type: counted once
            _sig(source_message_id="m2", event_date="2026-08-01"),
        ],
        gmail_scanned=3,
        scan_days=60,
    )
    (sub,) = reg["subscriptions"]
    assert len(sub["evidence"]) == 2
    assert sub["source_message_ids"] == ["m1", "m2"]
    assert sub["last_payment_date"] == "2026-08-01"
    assert sub["status"] == "active"
    assert sub["monthly_cost"] == 10.0 and sub["annual_cost"] == 120.0
    assert reg["source"] == {
        "gmail_messages_scanned": 3,
        "signals_extracted": 3,
        "calendar_events_scanned": 0,
    }


def test_merge_preserves_user_value_across_saves(tmp_path: Path) -> None:
    store = RegistryStore(path=tmp_path / "registry.json")
    reg = store.merge_signals([_sig()])
    reg["subscriptions"][0]["user_value"] = 2
    store.save(reg)
    again = store.merge_signals([_sig(source_message_id="m9")])
    assert again["subscriptions"][0]["user_value"] == 2


def test_usage_signals_match_merchant_case_insensitively(tmp_path: Path) -> None:
    store = RegistryStore(path=tmp_path / "registry.json")
    reg = store.merge_signals([_sig()], usage_by_merchant={"NOTION": ["Weekly planning"]})
    assert reg["subscriptions"][0]["usage_signals"] == ["Weekly planning"]


def test_rollup_unknown_cycle_uses_amount_heuristic() -> None:
    big: dict[str, Any] = {"amount": 240.0, "billing_cycle": "unknown"}
    small: dict[str, Any] = {"amount": 9.0, "billing_cycle": None}
    _rollup_costs(big)
    _rollup_costs(small)
    assert (big["billing_cycle"], big["monthly_cost"]) == ("annual", 20.0)
    assert (small["billing_cycle"], small["annual_cost"]) == ("monthly", 108.0)


def test_weekly_rollup() -> None:
    sub: dict[str, Any] = {"amount": 5.0, "billing_cycle": "weekly"}
    _rollup_costs(sub)
    assert sub["monthly_cost"] == 21.65 and sub["annual_cost"] == 260.0


def test_annual_renewal_from_leap_day_does_not_crash() -> None:
    # Bug: date(year + 1, 2, 29) raised ValueError and aborted the whole scan.
    sub: dict[str, Any] = {"last_payment_date": "2024-02-29", "billing_cycle": "annual"}
    _estimate_renewal(sub)
    nxt = date.fromisoformat(sub["next_renewal_date"])
    assert (nxt.month, nxt.day) == (2, 28)


def test_monthly_renewal_rolls_into_next_year() -> None:
    sub: dict[str, Any] = {"last_payment_date": "2099-12-31", "billing_cycle": "monthly"}
    _estimate_renewal(sub)
    assert sub["next_renewal_date"] == "2100-01-28"


def test_unparseable_payment_date_is_ignored() -> None:
    sub: dict[str, Any] = {"last_payment_date": "not-a-date", "billing_cycle": "monthly"}
    _estimate_renewal(sub)
    assert "next_renewal_date" not in sub
