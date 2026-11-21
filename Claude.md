# Project Overview: app_manager (Multi-App Django Backend + Mobile Clients)

`app_manager` is one Django backend serving **multiple client applications** from a single server (goal: avoid renting a server per app).
One repo, one DB, one Docker Compose stack; clients are isolated by `ClientApp` (see Core Design Rules). More clients may follow.

| Client (slug) | What | Mobile | Progress | Flow |
|---|---|---|---|---|
| **Saving** (`saving`) | Budget/tracking, bank statement parsing, investments, reporting | Flet, `mobile/` | `PROGRESS_saving.md` | `docs/FLOW_saving.md` |
| **Line Up** (`lineup`) | Data-driven card ordering game (timeline, streak, daily puzzle, invite challenges) | Flutter, `mobile_lineup/` | `PROGRESS_lineup.md` | `docs/FLOW_lineup.md` |

`docs/BRIEF_lineup.md` is the original Line Up brief (input only). **CLAUDE.md wins over any brief.**

## Tech Stack
- **Backend:** Python 3.14, Django 6.x, Django REST Framework, djangorestframework-simplejwt, PostgreSQL, Redis, Celery (+ celery-beat), Gunicorn.
- **Parsing:** pdfplumber (PDF statements), openpyxl (Excel statements, Line Up card import templates).
- **Mobile:** target **Android only**. Saving: Flet (Python/Flutter). Line Up: Flutter (Dart) with flutter_riverpod, go_router, dio
  (chosen because rewarded ads, subscriptions and FCM have no official Flet support).
- **Infra:** Docker Compose (Gunicorn + Nginx), two self-contained files:
  - **Development** (this PC): `docker-compose.yml`.
  - **Production** (home server, Windows 11, https://appmanager.com.tr): `docker-compose.prod.yml` = the same services + Cloudflare Tunnel; the server's `.env` sets `COMPOSE_FILE=docker-compose.prod.yml`. Keep shared services identical in both files. Deploy = push to GitHub (`origin`), then `git pull` + `docker compose up -d --build` on the server. See `docs/DEPLOY.md`.
- **Config:** `.env` via django-environ. `.env` is never committed; `.env.example` is.

## Directory Structure
```text
app_manager/                          # repo root
├── CLAUDE.md
├── PROGRESS_<slug>.md           # per-client phase/task tracking (PROGRESS_saving.md, PROGRESS_lineup.md)
├── docker-compose.yml           # development: nginx, web, db, redis, celery_worker, celery_beat
├── docker-compose.prod.yml      # production: same services + cloudflared tunnel
├── docs/                        # FLOW_<slug>.md (flow diagrams), DEPLOY.md (server setup / update), BRIEF_lineup.md
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
│   ├── notifications/           # shared: FCM sends, one Firebase project per client (fcm.py, `send_test_push <app>`)
│   ├── secrets/                 # git/docker-ignored keys: firebase-<app>.json (copied to the server by hand)
│   ├── saving_budget/           # accounts + computed balances, categories, transactions, payment plans (recurring/installment, auto-pay), monthly summary, statement parsing
│   ├── saving_invest/           # asset prices (gold, silver, USD, EUR), daily fetch, user portfolio
│   ├── saving_reports/          # aggregated reporting endpoints
│   ├── lineup_cards/            # card pool: flexible schema, importer.py (template -> preview -> staging),
│   │                            #   `seed_lineup_demo [--purge]` (fictional demo cards)
│   └── lineup_games/            # runs + moves API (/api/v1/lineup/games/); engine/ = pure-Python game engine,
│                                #   tests: `python manage.py test lineup_games`
├── mobile/                      # Saving: Flet 1.x Android client (pyproject.toml, own .venv)
│   ├── main.py                  # entry: builds AppState, ft.run(main)
│   ├── config.py                # API base URL per platform (SAVING_API_URL overrides)
│   ├── state.py / router.py     # session lifecycle, cached refs; view-stack navigation
│   ├── screens/                 # one module per feature; ui.py = shared helpers, choices.py = backend choice mirrors
│   └── services/                # api_client (async httpx, JWT auto-refresh), token_store, per-backend-app services
└── mobile_lineup/               # Line Up: Flutter Android client (applicationId tr.com.appmanager.lineup, provisional)
    └── lib/
        ├── main.dart / router.dart  # ProviderScope + MaterialApp.router; go_router redirects follow the session
        ├── config.dart          # API URL: debug -> http://10.0.2.2 (emulator), release -> production, --dart-define=API_URL
        ├── core/                # api_client (dio, JWT renewal: refresh -> guest re-login), token_store, models, providers
        └── features/<feature>/  # screens + Riverpod controllers + services (session/, home/, ...)
```
Planned later (decided in their phase): `lineup_social` (challenges), device tokens + Celery sends in `notifications`,
shared `billing` (AdMob SSV + subscription webhooks; client apps register reward handlers like `support.registry`).

### Working Across Clients (IMPORTANT)
- Before any change, identify the target client from the request (Saving: budget, statements, investments, reports, Flet;
  Line Up: cards, game modes, energy, Flutter). If unclear, ask.
- Touch only that client's apps (`<slug>_*`), its mobile folder and its `PROGRESS_<slug>.md`. Saving's mobile is Python/Flet
  (`mobile/`); Line Up's is Dart/Flutter (`mobile_lineup/`). Never port patterns between them blindly.
- A shared app (`accounts`, `support`, `core`, infra) changes only when needed, and must keep the other clients' behavior
  unchanged; say so explicitly when a change touches shared code.

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
8. **Line Up game rules:**
   - **Server-authoritative:** Django makes every game decision. A card's values are never sent before the move; the move
     response reveals them. Mobile only displays.
   - **Seeded, frozen decks:** a seed always yields the same deck for the same pool; the resolved card ids are stored on
     the run / daily puzzle / challenge at creation, so later pool changes never alter them.
   - **Engine:** `lineup_games/engine/` is pure Python (no ORM/request), takes plain DTOs; one generator class per mode
     holds its difficulty params (min value gap, popularity threshold, category mix).
   - **Flexible card model:** new categories need no migration. `Attribute` (comparable value: number or date + unit +
     compare labels) · `CardType` (schema: required/optional attributes, display fields) · `Card` (title, popularity
     0-100, status staging/approved/rejected, `external_key` for idempotent import, `extra` JSON for display-only
     fields such as team or region) · `CardValue` (typed: Decimal number or date + precision, own source) · hierarchical `Tag`.
   - **Ties:** dates keep their precision (year/month/day); two values equal at the coarser precision, or equal numbers,
     accept either order.
   - **No move timer** (removed 2026-11-22 by request): moves are never judged by time. `Move.elapsed_ms` is only recorded.
   - **Energy:** lazy, no cron: `energy = min(max, stored + (now - last) / refill)`. Daily puzzle and accepting a challenge never cost energy.
   - **Card values come from sources, never invented** (`source_url` is optional, not a review warning). Exception: demo
     cards from the seed command, flagged `is_demo`, purged before release. A card value whose attribute is missing from
     its type adds that attribute to the type as optional (admin save). One import pipeline; sources (Excel/CSV upload, later Wikidata) are adapters feeding it.
   - **Guests:** first launch creates a guest user (empty email allowed; email unique per app only when set); later link
     Google or set email + password.
   - Card error reports use the shared `support` app (registry key `lineup.card`).

## AI Operational Constraints (IMPORTANT)
- **NO Automatic Tests:** Do NOT generate tests unless explicitly requested. Exception: the Line Up game engine
  (`lineup_games/engine/`: deck generation, move validation, ties, timer, energy) is always covered by unit tests.
- **DB Actions (dev PC only):** Claude may run `makemigrations` and `migrate` on the development stack
  (`docker compose exec web python manage.py ...`), and small one-off data checks through `manage.py shell` that run
  inside one transaction and roll back (no leftovers). Never on the production server, and nothing destructive
  (flush, dropping/deleting data, `delete_account`, data-changing management commands) without asking first.
- **Shell Commands:** Run only what the user explicitly asked for (e.g. git init, docker build). Otherwise provide the commands.
- **Token Efficiency:** Keep responses concise. Edit only what is needed; don't rewrite whole files for small changes.
- **Small Steps:** Work in small task chunks and confirm before moving to the next phase.
- **Phase Workflow:** Every backend phase ends with its mobile counterpart (Flet for Saving, Flutter for Line Up) before the next phase starts. Mobile UI stays minimal and functional (logic first); visual design is a dedicated final phase.
- **Flow Diagram:** `docs/FLOW_<slug>.md` (Mermaid, Turkish labels) documents each client's end-to-end flow. Update it at the end of every phase (move items from planned/dashed to real, update the "Son güncelleme" line).
- **Progress Tracking:** `PROGRESS_<slug>.md` is the single source of truth for that client's phases/tasks. Read the relevant one at the start of a session; update it (checkboxes, notes, pending user commands) whenever a task is completed or the plan changes. Changes to shared apps/infra are noted in the progress file of the client that triggered them.
- **Commits:** the subject starts with the scope: `[saving] `, `[lineup] ` or `[shared] ` (shared apps, `core`, infra, docs for all clients). One scope per commit when practical, e.g. `[lineup] Card pool models and admin import`.
- **Language:** Respond in Turkish. Code, comments and identifiers are in English. User-facing API messages (validation/error `detail`) are in Turkish; keep machine-readable `code` values in English.
