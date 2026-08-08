# Value Investment API

FastAPI backend for the local value investment research workbench.

Current endpoint:

```text
GET /api/health
GET /api/companies
GET /api/companies/{company_id}
```

Database:

- SQLite file: `data/value_investment.db`
- ORM: SQLAlchemy 2.x
- Startup: tables are created automatically and seeded with a few demo companies
