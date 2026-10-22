"""Worth scoring and recommendation rules (pure functions, no I/O)."""

from __future__ import annotations

from typing import Any

from subscription_intelligence.recommendations.engine import (
    apply_recommendations,
    build_draft_actions,
)
from subscription_intelligence.scoring.worth import apply_scores


def _sub(name: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": name,
        "merchant": name.title(),
        "normalized_name": name,
        "evidence": [],
        "usage_signals": [],
        "user_value": None,
        "monthly_cost": None,
        "status": "active",
    }
    base.update(kw)
    return base


def test_payment_score_rewards_invoice_with_amount() -> None:
    reg = {
        "subscriptions": [
            _sub(
                "notion",
                evidence=[{"event_type": "invoice", "amount": 10.0, "confidence": 1.0}],
                last_payment_date="2026-07-01",
            ),
            _sub("nothing"),
        ]
    }
    apply_scores(reg)
    paid, empty = reg["subscriptions"]
    assert paid["payment_evidence_score"] == 0.75  # 0.45 invoice + 0.2 amount + 0.1 date
    assert empty["payment_evidence_score"] == 0.0


def test_usage_score_buckets() -> None:
    reg = {"subscriptions": [_sub(f"s{n}", usage_signals=["x"] * n) for n in (0, 1, 3, 5)]}
    apply_scores(reg)
    assert [s["usage_evidence_score"] for s in reg["subscriptions"]] == [0.0, 0.35, 0.6, 0.85]


def _recommend(**kw: Any) -> dict[str, Any]:
    reg = {"subscriptions": [_sub("tool", **kw)]}
    return apply_recommendations(reg)["subscriptions"][0]


def test_weak_payment_evidence_is_investigated() -> None:
    assert _recommend(payment_evidence_score=0.2)["recommendation"] == "investigate"


def test_low_user_value_with_payment_is_cancel() -> None:
    sub = _recommend(payment_evidence_score=0.8, user_value=1)
    assert sub["recommendation"] == "cancel"


def test_high_user_value_is_kept_even_without_usage() -> None:
    sub = _recommend(payment_evidence_score=0.8, usage_evidence_score=0.0, user_value=5)
    assert sub["recommendation"] == "keep"


def test_paid_but_unused_is_cancel_and_gets_a_draft_action() -> None:
    reg = {
        "subscriptions": [
            _sub("tool", payment_evidence_score=0.7, usage_evidence_score=0.0, monthly_cost=12)
        ]
    }
    apply_recommendations(reg)
    assert reg["subscriptions"][0]["recommendation"] == "cancel"
    (draft,) = reg["draft_actions"]
    assert draft["status"] == "draft" and draft["action"] == "cancel"


def test_overlapping_tools_mark_the_less_used_as_duplicate() -> None:
    reg = {
        "subscriptions": [
            _sub("chatgpt", payment_evidence_score=0.6, usage_evidence_score=0.85),
            _sub("claude", payment_evidence_score=0.6, usage_evidence_score=0.35),
        ]
    }
    apply_recommendations(reg)
    used, other = reg["subscriptions"]
    assert used.get("duplicate_of") is None
    assert other["duplicate_of"] == "chatgpt"


def test_human_decisions_on_draft_actions_are_kept() -> None:
    reg = {
        "subscriptions": [
            _sub("tool", recommendation="cancel", recommendation_reason="unused"),
        ],
        "draft_actions": [
            {"subscription_id": "tool", "action": "cancel", "status": "rejected"},
        ],
    }
    (draft,) = build_draft_actions(reg)
    assert draft["status"] == "rejected"
