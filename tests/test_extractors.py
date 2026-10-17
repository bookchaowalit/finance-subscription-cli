"""Unit tests for signal extractors (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from subscription_intelligence.extractors.signals import extract_signals_from_message
from subscription_intelligence.gmail_adapter.client import MessageMeta
from subscription_intelligence.recommendations.engine import apply_recommendations
from subscription_intelligence.reports.builder import build_report, format_report_text
from subscription_intelligence.scoring.worth import apply_scores


def _msg(**kwargs) -> MessageMeta:
    base = {
        "id": "m1",
        "thread_id": "t1",
        "from_address": "billing@notion.so",
        "from_name": "Notion",
        "subject": "Your Notion invoice",
        "date": "2026-07-01",
        "snippet": "Thanks for your payment of $10.00 USD for your monthly subscription.",
        "labels": ["INBOX"],
    }
    base.update(kwargs)
    return MessageMeta(**base)


def test_extract_invoice_notion():
    sigs = extract_signals_from_message(_msg())
    assert len(sigs) == 1
    s = sigs[0]
    assert s.merchant == "Notion"
    assert s.event_type in {"invoice", "receipt", "payment", "renewal"}
    assert s.amount == 10.0
    assert s.currency == "USD"
    assert s.billing_cycle == "monthly"
    assert s.confidence > 0.5


def test_extract_vercel_renewal():
    sigs = extract_signals_from_message(
        _msg(
            id="m2",
            from_address="noreply@vercel.com",
            from_name="Vercel",
            subject="Your annual plan will renew soon",
            snippet="Vercel Pro annual renewal of $240.00 USD on your account.",
        )
    )
    assert sigs
    assert sigs[0].merchant == "Vercel"
    assert sigs[0].amount == 240.0


def test_pipeline_scores_and_report():
    from subscription_intelligence.subscription_registry.store import (
        RegistryStore,
    )

    store = RegistryStore(path=Path("/tmp/si-test-registry.json"))
    if store.path.exists():
        store.path.unlink()

    signals = extract_signals_from_message(_msg())
    # unused service
    signals += extract_signals_from_message(
        _msg(
            id="m3",
            from_address="billing@capacities.io",
            from_name="Capacities",
            subject="Payment receipt",
            snippet="We received your payment of $12 USD monthly membership.",
            date="2026-06-01",
        )
    )
    reg = store.merge_signals(signals, gmail_scanned=2, scan_days=30)
    reg = apply_scores(reg)
    reg = apply_recommendations(reg)
    store.save(reg)

    assert reg["subscriptions"]
    report = build_report(reg, within_days=365)
    text = format_report_text(report)
    assert "Upcoming renewals" in text
    assert "Recommended actions" in text

    store.path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_extract_invoice_notion()
    test_extract_vercel_renewal()
    test_pipeline_scores_and_report()
    print("OK")
