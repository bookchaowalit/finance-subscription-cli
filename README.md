# Subscription Intelligence

**Status:** MVP (CLI + registry + report)  
**Temporary name:** Subscription Intelligence  
**Repo:** https://github.com/bookchaowalit/finance-subscription-cli  
**Boundary:** Product logic lives here. Solo Empire `infra/` is an **integration layer only**.

## Placement (Solo Empire workspace)

This is a **standalone GitHub product** (own `.git`), not a Solo Empire monorepo package.
Checkout follows the book-dev hierarchy:

```text
book-dev/
└── github/
    └── bookchaowalit/              # owner
        └── book-products/
            └── subscription-intelligence/   # this repo
```

| Role | Path |
|------|------|
| **Canonical local clone** | `domains/product/engineering/book-dev/github/bookchaowalit/book-products/subscription-intelligence` |
| **GitHub** | https://github.com/bookchaowalit/finance-subscription-cli |
| Solo Empire tracking | ignored via `domains/product/engineering/*` — product has its own git |

Catalog: `solo-empire/docs/projects/projects.yaml` + `REGISTRY.md`.

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

## Safety

- Read-only Gmail/Calendar API usage in product code  
- Cancel flow = human-approved checklist only  
- Secrets stay in Solo Empire `.env`; never commit `data/` registry

## Roadmap

1. **Now** — CLI scan / report / renewals  
2. Next — stronger amount extraction (ephemeral body parse) + `rate` command  
3. Later — dashboard  
4. Later — optional Todoist tasks for approved cancel/investigate  
