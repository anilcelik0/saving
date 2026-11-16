# Project Overview: app_manager (Multi-App Django Backend + Flet)

`app_manager` is one Django backend serving **multiple client applications** from a single server (goal: avoid renting a server per app).
First client: **Saving** (Android app built with Flet), which includes budget/tracking, bank statement parsing, investments and reporting.

## Tech Stack
- **Backend:** Python 3.14, Django 6.x, Django REST Framework, djangorestframework-simplejwt, PostgreSQL, Redis, Celery (+ celery-beat), Gunicorn.
- **Parsing:** pdfplumber (PDF statements), openpyxl (Excel statements).
- **Mobile:** Flet (Python/Flutter), target **Android only**.
- **Infra:** Docker Compose (Gunicorn + Nginx), two self-contained files:
  - **Development** (this PC): `docker-compose.yml`.
  - **Production** (home server, Windows 11, https://appmanager.com.tr): `docker-compose.prod.yml` = the same services + Cloudflare Tunnel; the server's `.env` sets `COMPOSE_FILE=docker-compose.prod.yml`. Keep shared services identical in both files. Deploy = push to GitHub (`origin`), then `git pull` + `docker compose up -d --build` on the server. See `docs/DEPLOY.md`.
- **Config:** `.env` via django-environ. `.env` is never committed; `.env.example` is.

## Directory Structure
```text
app_manager/                          # repo root
├── CLAUDE.md
├── docker-compose.yml           # development: nginx, web, db, redis, celery_worker, celery_beat
├── docker-compose.prod.yml      # production: same services + cloudflared tunnel
├── docs/                        # FLOW.md (flow diagram), DEPLOY.md (server setup / update)
├── .env / .env.example
├── nginx/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt         # single file, pinned versions
│   ├── manage.py
│   ├── core/                    # Django project package: settings.py, urls.py, celery.py, wsgi/asgi, base_models.py
│   ├── accounts/                # shared: ClientApp registry + app-scoped users + JWT auth + legal docs/consents
│   ├── legal_texts/<app>/       # privacy.md, kvkk.md -> `publish_legal_documents <app>` (versioned in DB)
│   ├── support/                 # shared: issue reports ("Sorun bildir") + attachments; client apps register
│   │                            #   related-object snapshots in support.registry (e.g. "saving.statement")
│   ├── saving_budget/           # accounts + computed balances, categories, transactions, payment plans (recurring/installment, auto-pay), monthly summary, statement parsing
│   ├── saving_invest/           # asset prices (gold, silver, USD, EUR), daily fetch, user portfolio
│   └── saving_reports/          # aggregated reporting endpoints
└── mobile/                      # Flet 1.x Android client (pyproject.toml, own .venv)
    ├── main.py                  # entry: builds AppState, ft.run(main)
    ├── config.py                # API base URL per platform (SAVING_API_URL overrides)
    ├── state.py / router.py     # session lifecycle, cached refs; view-stack navigation
    ├── screens/                 # one module per feature; ui.py = shared helpers, choices.py = backend choice mirrors
    └── services/                # api_client (async httpx, JWT auto-refresh), token_store, per-backend-app services
```

### App Naming Convention
- Client-specific apps: `<clientapp>_<feature>` (e.g. `saving_budget`, a future `otherapp_orders`).
- Shared apps used by all clients have no prefix (e.g. `accounts`).
- Client apps may depend on shared apps. Shared apps never depend on client apps. Apps of different clients never depend on each other.

## Core Design Rules
1. **Multi-App Identity:** A `ClientApp` model (slug, e.g. `saving`) registers each client application. No hard-coded choices, so new apps need no migration.
   - A user account is scoped to one app: `UniqueConstraint(email, app)` and `UniqueConstraint(username, app)`.
   - The same email can register in different apps with **separate passwords** (separate account rows).
   - Login = (email or username) + password + app identifier. Uses a custom auth backend.
   - JWT tokens carry an `app` claim. Every request is validated against that app, so a token from app A cannot access app B.
2. **API-First:** All business logic (parsing, calculations, price fetching, reports) lives in Django. Flet is a thin client consuming versioned JSON APIs (`/api/v1/...`) with JWT.
3. **Data Isolation:** All user-owned data is scoped to the user (and so to the app). Querysets are always filtered by `request.user`.
4. **Money:** Currency is TRY. Use `DecimalField` (never float) for amounts, asset quantities and prices.
5. **Statement Parsing:** Lives in `saving_budget/statements`. One layout-driven engine for every bank (no per-bank parser classes, by request 2026-11-16): PDF words with positions → date rows → amount columns found from alignment and named by the header (or by the data, e.g. running balance); Turkish/US number formats per token; Excel via the same header keywords. Bank/type are recognized from the text (`profiles.py`). Every result carries a self-check against the statement totals (card: previous + rows = debt; account: running balance) shown on the preview. Returns normalized DTOs; parsing runs as a Celery task, not inside the request. Never read card numbers or personal fields.
6. **Market Data:** Lives in `saving_invest`. Prices come from a free external API, fetched **once per day** by a celery-beat task and stored as historical rows. The provider sits behind an adapter so it can be swapped.
7. **Settings:** Single `settings.py`. All secrets, hosts and flags come from env variables.

## AI Operational Constraints (IMPORTANT)
- **NO Automatic Tests:** Do NOT generate tests unless explicitly requested.
- **NO Automatic DB Actions:** Never run `makemigrations`, `migrate` or DB shell/checks automatically. Provide the commands instead.
- **Shell Commands:** Run only what the user explicitly asked for (e.g. git init, docker build). Otherwise provide the commands.
- **Token Efficiency:** Keep responses concise. Edit only what is needed; don't rewrite whole files for small changes.
- **Small Steps:** Work in small task chunks and confirm before moving to the next phase.
- **Phase Workflow:** Every backend phase ends with its mobile (Flet) counterpart before the next phase starts. Mobile UI stays minimal and functional (logic first); visual design is a dedicated final phase.
- **Flow Diagram:** `docs/FLOW.md` (Mermaid, Turkish labels) documents the end-to-end flow. Update it at the end of every phase (move items from planned/dashed to real, update the "Son güncelleme" line).
- **Progress Tracking:** `PROGRESS.md` is the single source of truth for phases/tasks. Read it at the start of a session; update it (checkboxes, notes, pending user commands) whenever a task is completed or the plan changes.
- **Language:** Respond in Turkish. Code, comments and identifiers are in English. User-facing API messages (validation/error `detail`) are in Turkish; keep machine-readable `code` values in English.
