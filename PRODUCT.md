# Subscription Intelligence (finance-subscription-cli) — Product brief

**Repo:** `bookchaowalit/finance-subscription-cli` (public, AGPL-3.0)
**Status:** MVP CLI for one operator. No hosted service, no live URL.
**Updated:** 2026-10-22

## Purpose

Find out which personal subscriptions you pay for, when they renew and whether
they are still worth it, from read-only Gmail and Google Calendar data.

## Users

One operator (the owner) running the CLI locally with their own Google OAuth grant.

## What works today

- `scan`: reads Gmail message metadata and snippets (GET only), extracts invoice /
  receipt / renewal / trial / price-increase / cancellation-link signals with
  rule-based patterns, optionally matches Calendar event titles as usage evidence,
  and merges everything into `data/registry.json`.
- Scoring: payment evidence, usage evidence, and an optional manual `user_value` (1–5).
- Recommendations: keep / downgrade / cancel / investigate, duplicate detection across
  overlapping tools, and a **draft** cancel/investigate checklist that is never executed.
- `report` (text or `--json`) and `renewals --within 90d`.

## How to run

```bash
uv sync --frozen --all-extras
# Credentials come from the environment (inject from your secret manager):
#   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
./bin/subscription-intel scan --days 365
./bin/subscription-intel report
```

Checks (same as CI): `ruff check . && ruff format --check . && mypy . && pytest --cov`.

## AI / LLM

No LLM provider is called. Names such as OpenAI, Anthropic, ChatGPT or Claude in
`extractors/signals.py` and `recommendations/engine.py` are merchant names to detect
as subscriptions. The only outbound hosts are `gmail.googleapis.com`,
`www.googleapis.com/calendar` and `oauth2.googleapis.com/token`. Extraction is
regex/keyword based; there is no eval set for extraction accuracy (gap).

## Limits

- Extraction is heuristic: amounts and cycles are missed when the snippet lacks them.
- Calendar scan reads one page of at most 250 events; no pagination.
- Monthly renewal estimates clamp the day to 28; renewals far in the past are rolled
  forward only once, so very stale subscriptions can show a past renewal date.
- No runtime to monitor (local CLI), so no Sentry.
- Local data has no automatic retention/expiry (see README "Retention").
- Test coverage 57.96% (2026-10-22): the Gmail/Calendar adapters and the CLI wiring are untested.

## Disposition

Keep as a personal tool. Roadmap in README.
