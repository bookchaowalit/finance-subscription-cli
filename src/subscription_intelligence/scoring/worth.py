"""
Three-layer worth model:

1. payment_evidence_score — real spend signals from email
2. usage_evidence_score — activity / calendar references
3. user_value — manual 1–5 (left null until user rates)
"""

from __future__ import annotations

from typing import Any


def apply_scores(registry: dict[str, Any]) -> dict[str, Any]:
    for sub in registry.get("subscriptions", []):
        sub["payment_evidence_score"] = _payment_score(sub)
        sub["usage_evidence_score"] = _usage_score(sub)
        # user_value left as-is (manual)
    return registry


def _payment_score(sub: dict[str, Any]) -> float:
    evidence = sub.get("evidence") or []
    if not evidence:
        return 0.0
    types = {e.get("event_type") for e in evidence}
    score = 0.0
    if types & {"invoice", "receipt", "payment"}:
        score += 0.45
    if "renewal" in types:
        score += 0.25
    if "trial" in types:
        score += 0.15
    if "price_increase" in types:
        score += 0.15
    if "cancellation_link" in types:
        score += 0.2  # subscription-shaped mail even without amount
    if any(e.get("amount") is not None for e in evidence):
        score += 0.2
    if sub.get("last_payment_date"):
        score += 0.1
    if len(evidence) >= 2:
        score += 0.05
    # average confidence ceiling
    confs = [float(e.get("confidence") or 0) for e in evidence]
    if confs:
        score = min(1.0, score * (0.5 + 0.5 * (sum(confs) / len(confs))))
    return round(min(1.0, score), 3)


def _usage_score(sub: dict[str, Any]) -> float:
    signals = sub.get("usage_signals") or []
    n = len(signals)
    if n == 0:
        return 0.0
    if n == 1:
        return 0.35
    if n <= 3:
        return 0.6
    return 0.85
