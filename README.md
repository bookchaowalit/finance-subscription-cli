# Subscription Intelligence

**Status:** MVP (CLI + registry + report)  
**Temporary name:** Subscription Intelligence  
**Repo:** https://github.com/bookchaowalit/finance-subscription-cli  
**Boundary:** Product logic lives here. Solo Empire `infra/` is an **integration layer only**.

## Placement (Solo Empire workspace)

This is a **standalone GitHub product** (own `.git`), not a Solo Empire monorepo package.
The current checkout is
`projects/product/engineering/book-dev/github/bookchaowalit/public/book-products/finance-subscription-cli`.
The historical repository name was `subscription-intelligence`; the canonical
remote is https://github.com/bookchaowalit/finance-subscription-cli.

## What it does

Read-only intelligence over personal subscriptions:

1. **Gmail (read-only)** — invoices, receipts, renewals, trials, price increases, cancellation links  
2. **Calendar** — usage evidence (events that mention a merchant/tool)  
3. **Registry** — normalize into a subscription registry  
4. **Scoring** — “is it worth it?” in three independent layers  
5. **Recommendations** — Keep / Downgrade / Cancel / Investigate / Consider subscribing  
6. **Reports** — renewals, unused, duplicates, action list  

### Non-goals (MVP)

- Does **not** label, star, archive, or delete Gmail messages  
- Does **not** auto-unsubscribe or cancel  
- Does **not** store full email bodies by default  
- Does **not** write into Solo Empire core CRM/DB business tables  

Cancel/unsubscribe becomes a **draft checklist** for human approval.

## Worth-it model (3 layers)

| Layer | Question | Source |
|-------|----------|--------|
| **Payment evidence** | Is there real spend? | Gmail invoice/receipt/renewal signals |
| **Usage evidence** | Any activity / calendar reference? | Calendar titles |
| **User value** | Do *you* still need it? | Manual score (`user_value` 1–5) |

## Layout

```
subscription-intelligence/
├── README.md
├── pyproject.toml
├── bin/subscription-intel
├── src/subscription_intelligence/
│   ├── gmail_adapter/          # Gmail API read-only
│   ├── calendar_adapter.py
│   ├── extractors/
│   ├── subscription_registry/
│   ├── scoring/
│   ├── recommendations/
│   ├── reports/
│   └── cli/
├── schema/
├── tests/
└── data/                       # local only (gitignored)
```

## Integration boundary

| Need | Source |
|------|--------|
| Google OAuth | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` environment variables |
| HTTP + token refresh | `src/subscription_intelligence/http_util.py` (vendored, stdlib only) |
| Product data | this repo `data/` only |

Credentials are never bundled; supply them through the environment.

## CLI

```bash
# From this repo
./bin/subscription-intel scan --days 365
./bin/subscription-intel scan --days 90 --fresh
./bin/subscription-intel report
./bin/subscription-intel renewals --within 90d
./bin/subscription-intel report --json
```

## Permissions

The intended external OAuth grant is limited to these read-only scopes:

| Scope | Current adapter use |
| --- | --- |
| `https://www.googleapis.com/auth/gmail.readonly` | Read profile, search subscription message IDs, fetch metadata and snippets. |
| `https://www.googleapis.com/auth/calendar.events.readonly` | List events on the primary calendar for merchant-title usage matches; omit this grant and use `--no-calendar` for Gmail-only scans. |

References: [Google Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
and [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth).

The CLI does **not** run an OAuth consent flow or declare scopes in `src/`.
`infra_bridge.py` reads externally supplied credential environment variables;
`http_util.get_access_token` refreshes that existing grant without requesting a
scope. It does not inspect or restrict the granted token's scopes. A source scan
finding no write scope is therefore **not proof** that an externally supplied
token has only read-only permissions. Provision a dedicated read-only grant;
this document does not claim that any account grant has been verified.

The Gmail and Calendar adapters issue GET requests only. The token refresh is a
POST to the OAuth token endpoint, not a mailbox/calendar mutation. There are no
send, label, archive, delete, event-write or automatic cancellation operations.
Cancellation URLs are stored as checklist evidence and are not followed by the CLI.

## Retention

**Current rule: local extracted data persists until the operator removes it.**
There is no automatic expiration, TTL, age-based pruning, encryption-at-rest or
scheduled cleanup implemented by this product. In particular, `--days` limits
the scan query; it does not expire previously saved evidence.

| Data | Storage and lifetime |
| --- | --- |
| Subscription registry | `data/registry.json`, overwritten on save while merging existing subscriptions and deduplicating evidence. Stores merchant/name, amounts/currency/cycle, payment/renewal dates, scores, recommendations, optional user value, timestamps and scan counters. |
| Message evidence | Inside the registry: source message IDs, event type/date, amount/currency, confidence, snippet/subject fallback truncated to 280 characters, and cancellation/unsubscribe URLs. Such URLs may contain personal identifiers. Full bodies and attachments are not fetched or persisted by the current metadata adapter. |
| Calendar evidence | Matching title fragments (up to 80 characters) with start date/time are saved as usage signals, capped at 20 per subscription. Unmatched event objects are held only during the scan; the full calendar is not written to disk. |
| Draft actions | Registry entries include merchant, subscription ID, action/status, reason/notes, URL and creation time. These are local checklists, not executed provider changes. |
| Text report | `report` without `--json` overwrites `data/reports/latest-report.txt`. JSON reports and renewal output go to stdout; any redirected files or captured logs have their own operator-managed lifetime. |
| Credentials | Supplied through process environment, not written by this product. Access tokens live in process memory. Removing product files does not revoke the external grant or delete credentials from a secret manager. |

`scan --fresh` replaces subscriptions after fetching new evidence, but initially
keeps prior actions with `approved`, `done` or `rejected` status; recommendation
rebuilding then carries forward actions matching current recommendations. It
also leaves the existing text report untouched. **It is not a complete erasure
command.** A normal merge has no evidence-age or subscription-count cap.

For complete local removal, stop scans and remove `data/registry.json` and
`data/reports/latest-report.txt` from this checkout, plus any reports/logs you
saved elsewhere and their backups. A subsequent scan recreates extracted data.
Deleting local files does not alter source Gmail/Calendar data. This manual
retention rule is a description of current behavior, not a legal approval or a
claim of a timed deletion guarantee. Keep local data and exports out of Git.

### Collection limits

Gmail scans default to 365 lookback days and at most 200 matching messages
(`--days` / `--max`). Calendar scanning uses at most 180 days back and 30 days
forward; it requests one page of at most 250 events and does not paginate.
Missing/failed metadata fetches are skipped; Calendar request failures return
an empty result, so absence of a usage signal is not proof of non-use. These
collection bounds do not limit the age or overall size of the saved registry.

## Offline verification

No Google account or credentials are needed for the test suite (synthetic messages,
HTTP mocked, temp files only):

```bash
uv sync --frozen --all-extras
uv run ruff check . && uv run mypy . && uv run pytest -q
# Scope-literal audit: currently no declarations in src (zero matches).
rg -n 'googleapis.com/auth/' src
```

The last command currently exits 1 because there are no matches. Inspect any
future matches and require read-only scopes; do not treat this audit as token
scope validation.

## Safety

- Read-only Gmail/Calendar API usage in product code  
- Cancel flow = human-approved checklist only  
- Credentials come from the process environment; never commit secrets, the registry or reports

## Roadmap

1. **Now** — CLI scan / report / renewals  
2. Next — stronger amount extraction (ephemeral body parse) + `rate` command  
3. Later — dashboard  
4. Later — optional Todoist tasks for approved cancel/investigate  
