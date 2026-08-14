# Value Investment API

FastAPI backend for the local value investment research workbench.

Current endpoint:

```text
GET /api/health
GET /api/companies
POST /api/companies
GET /api/companies/{company_id}
POST /api/companies/{company_id}/profile/refresh
GET /api/companies/{company_id}/financials
POST /api/companies/{company_id}/financials/sync
DELETE /api/companies/{company_id}/financials/{statement_id}
GET /api/companies/{company_id}/announcements
POST /api/companies/{company_id}/announcements/sync
POST /api/companies/{company_id}/announcements/summarize-all
POST /api/companies/{company_id}/announcements/summarize-all-deep
POST /api/companies/{company_id}/announcements/{announcement_id}/summarize
DELETE /api/companies/{company_id}/announcements/{announcement_id}
GET /api/evidence/model-config
POST /api/evidence/model-smoke-test
POST /api/companies/{company_id}/evidence/search
GET /api/companies/{company_id}/evidence
GET /api/evidence/{evidence_id}
POST /api/evidence/{evidence_id}/review
DELETE /api/evidence/{evidence_id}
GET /api/analyst-profiles
GET /api/companies/{company_id}/analysis/runs/latest
GET /api/companies/{company_id}/analysis/runs
POST /api/companies/{company_id}/analysis/runs
POST /api/companies/{company_id}/analysis/runs/batch
DELETE /api/companies/{company_id}/analysis/runs/{run_id}
```

Financial sync:

- `GET /api/companies/{company_id}/financials` reads stored financial statements.
- `POST /api/companies/{company_id}/financials/sync?limit=60` searches about 15 years of external financial data and upserts it into the database.
- `DELETE /api/companies/{company_id}/financials/{statement_id}` removes one stored financial statement from the local database.
- The current MVP data source is Eastmoney F10 main financial indicators. AkShare is not required for this first sync path.

Announcement sync:

- `GET /api/companies/{company_id}/announcements` reads stored announcements.
- `POST /api/companies/{company_id}/announcements/sync?years=1` searches up to 50 public announcements from the last year, upserts them into the database, and prunes older or overflow stored announcements for that company.
- `POST /api/companies/{company_id}/announcements/summarize-all` generates fast metadata-only summaries for the current announcement list and skips already deep-summarized items.
- `POST /api/companies/{company_id}/announcements/summarize-all-deep` processes pending announcements one by one with the backend model gateway and skips already deep-summarized items.
- `POST /api/companies/{company_id}/announcements/{announcement_id}/summarize` generates one structured announcement summary through the backend model gateway and stores only the latest summary on the announcement row.
- `DELETE /api/companies/{company_id}/announcements/{announcement_id}` removes one stored announcement scoped to that company.
- The current MVP data source is Eastmoney announcements and first supports A-share tickers such as `600519.SH`.
- Announcement sync does not call any model API or filter announcements by price/sentiment keywords. It skips already stored announcements and does not overwrite existing summaries. Summary generation is a separate stateless backend action and does not reuse model messages or historical runs unless explicitly added by a future service.
- Announcement status is derived from `summary_model_name`: empty means `未摘要`, `metadata_keyword` means `已快速摘要`, and any other non-empty model name means `已深度摘要`.
- Announcement evidence for the analyst layer is intentionally narrow: `id`, `title`, `published_at`, `category`, `summary`.

External evidence:

- `GET /api/evidence/model-config` returns model gateway configuration status without exposing the API key.
- `POST /api/evidence/model-smoke-test` checks whether the configured OpenAI-compatible model can return structured JSON.
- `POST /api/companies/{company_id}/evidence/search` asks the model to plan and summarize external evidence, then stores reviewed candidates in the local database.
- `GET /api/companies/{company_id}/evidence` reads stored external evidence for one company.
- `GET /api/evidence/{evidence_id}` reads one evidence record.
- `POST /api/evidence/{evidence_id}/review` marks one evidence record as manually reviewed.
- `DELETE /api/evidence/{evidence_id}` removes one stored evidence record.

Analyst views:

- `GET /api/analyst-profiles` lists registered analyst profiles.
- `GET /api/companies/{company_id}/analysis/runs/latest` reads latest analysis runs, defaulting to latest successful analyst views.
- `GET /api/companies/{company_id}/analysis/runs` reads analysis run history with optional filters.
- `POST /api/companies/{company_id}/analysis/runs` generates one analyst view from the current stored company snapshot.
- `POST /api/companies/{company_id}/analysis/runs/batch` generates multiple analyst views independently.
- `DELETE /api/companies/{company_id}/analysis/runs/{run_id}` deletes one stored analysis run.

Company profile refresh:

- `GET /api/companies/{company_id}` reads the stored company profile and attempts to fill a missing A-share listed date without blocking the response.
- `POST /api/companies/{company_id}/profile/refresh` refreshes listed date plus profile display fields: market cap, current price, TTM/dynamic/static PE, PB, PS, TTM dividend yield, source, source URL, and market-data update time.
- The current market snapshot source is Eastmoney quote snapshot with a `push2delay` fallback. TTM dividend yield is calculated from Eastmoney F10 bonus-financing data as implemented cash dividend per share over current price. Unsupported tickers return `400`; source/network failures return `502`.

Database:

- SQLite file: `data/value_investment.db`
- ORM: SQLAlchemy 2.x
- Startup: tables are created automatically and seeded with real A-share, HK-share, and US-share company master data.
