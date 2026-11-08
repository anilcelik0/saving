# PROGRESS

Phase and task tracking. Update this file whenever a task is completed or the plan changes.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo

---

## ⏳ Waiting on user (pending commands)

- [ ] Try the mobile app on desktop: `cd mobile; .venv\Scripts\flet run` (backend must be up)

---

## Phase 0: Infrastructure & skeleton ✅
- [x] git init, `.gitignore`, `.gitattributes`
- [x] First commit
- [x] `.env` / `.env.example`
- [x] `backend/requirements.txt` (pinned, Python 3.14 compatible)
- [x] `backend/Dockerfile` (python:3.14-slim, non-root user, Gunicorn)
- [x] `nginx/default.conf` (static/media, dynamic DNS for `web`)
- [x] `docker-compose.yml`: nginx, web, db (postgres 18), redis 8, celery_worker, celery_beat
- [x] `core` package: settings, urls, celery, wsgi/asgi, `base_models.py` (UUIDv7 + timestamps)
- [x] DRF + simplejwt base config, `/api/v1/health/`
- [x] Empty apps registered: accounts, saving_budget, saving_invest, saving_reports
- [x] Gunicorn `--reload` (code changes picked up live via polling)

## Phase 1: accounts ✅
- [x] `ClientApp` model + `create_client_app` management command
- [x] Custom `User` (UUIDv7, unique username/email per app, app=NULL means platform admin)
- [x] `AppScopedBackend` (username/email + password + app; admin login uses platform accounts only)
- [x] JWT `app` claim (`issue_tokens`), `AppJWTAuthentication` (claim + active app check)
- [x] `app_permission("<slug>")` permission factory for client apps
- [x] Endpoints: `auth/register`, `auth/login`, `auth/refresh`, `auth/logout` (blacklist), `auth/me` (GET/PATCH)
- [x] Throttling for register/login (`auth`: 10/min)
- [x] Migrations + seed `saving` app + superuser (run by user)
- [x] API smoke test: register (dup/weak password/unknown app errors), login by email (case-insensitive),
      wrong password/app → 401, me GET/PATCH (email read-only), refresh rotation + blacklist, logout
- [ ] (Later) Change password, password reset by email
- [x] Turkish API error messages (custom + simplejwt token errors via `core.exceptions.api_exception_handler`)
- [x] Long-lived sliding session: access 30 min, refresh 90 days rotated on every refresh;
      refresh checks user/app still active (`AppTokenRefreshSerializer`); daily `flushexpiredtokens` beat task (04:00)
- [ ] (Later) Test a second ClientApp to verify the cross-app token rejection in practice

## Phase 2: saving_budget 🔄
### 2a: Core budget — single Transaction model (redesign 2026-11-09)
- [x] **Transaction is the only money-movement model**: date + status (pending/paid) + auto_pay. Only paid affects balance.
- [x] `Series` = internal repeat rule grouping occurrences (never a separate screen):
      installment → all N pending rows created upfront (total split, remainder on last);
      recurring → rows generated 12 months ahead; daily task tops up when < 60 days remain
- [x] One-time entry: date ≤ today → paid, future → pending
- [x] Edit/delete series occurrences with `?scope=this|following` (following: shared fields to later pending rows +
      series template; delete following stops the series, paid history kept)
- [x] `transactions/upcoming/?days=30` (pending incl. overdue), `transactions/{id}/pay/` (amount may change), `/unpay/`
- [x] `summary/?month=`: month income/expense split paid/pending (each month on its own), current balance,
      overdue totals, projected month-end balance (all pending up to month end incl. overdue)
- [x] Daily beat 00:30 `daily_budget_maintenance`: auto-pay settle + series extension
- [x] Account: bank/cash + opening_balance; Removed: goals, PaymentPlan, account bank/last4
- [x] Shared helpers: `core.viewsets.OwnedModelViewSet`, `core.serializers.OwnedPrimaryKeyRelatedField`, ProtectedError → 409,
      `?page_size=` (max 100); default categories on saving registration
- [x] Migration reset (user) + API smoke test (monthly totals non-cumulative, installments, scope edit/delete, pay/unpay, daily task simulated in rollback)

### 2a-mobile (logic only, minimal UI)
- [x] Flet 1.1.2 project (`mobile/pyproject.toml`, `.venv`), async httpx `ApiClient`
- [x] Auth: login, register, auto-login with stored tokens, logout, session-expired → login
- [x] Auto refresh on 401 (single-flight lock, retries request once)
- [x] 3 tabs: Summary (month nav, income/expense with paid/pending, account balances, overdue, month-end projection),
      Activity "Hareketler" (Pending 30 days incl. overdue with quick pay + paid History; one "+" = entry form:
      one-time / recurring / installment + auto-pay; edit/delete asks scope for series; mark paid / undo),
      More (accounts, categories, profile, logout)
- [x] Turkish money input: "300.000" = 300000, "1.234,50" = 1234.50
- [x] Headless smoke test after migration (entry types, quick pay with changed amount, scope edit, summary per month)
- [ ] Manual check in the real Flet window (date picker, dropdowns)
- [ ] (Later) Payment reminder (push notification), "skip this period" action, transfer between accounts (bank ↔ cash)

### 2b: Statement parsing
- [ ] Statement upload model + file storage
- [ ] Parser registry + normalized transaction DTO
- [ ] First bank parsers (PDF/Excel) — need sample statements from user
- [ ] Celery parse task, import into transactions, duplicate detection

## Phase 3: saving_invest
- [ ] Pick free price API (gold, silver, USD, EUR) + adapter
- [ ] Asset & PriceHistory models, daily celery-beat task
- [ ] Portfolio holdings + valuation endpoints

## Phase 4: saving_reports
- [ ] Category breakdown, monthly trends, portfolio value (basic month totals/balances already in `saving_budget` summary)

## Phase 5: Mobile finalization (per-phase mobile work is done inside each phase)
- [ ] Secure token storage (SharedPreferences is not encrypted)
- [ ] Android build (`flet build apk`), cleartext HTTP / real-device API URL config
- [ ] Visual design pass (last)

---

## Notes / Decisions
- No django-celery-beat: schedules live in code (`CELERY_BEAT_SCHEDULE`).
- No CORS package: Android native client does not need it.
- Local runs production-like (`DEBUG=False`); errors are visible in `docker compose logs web`.
- Android emulator reaches the host via `10.0.2.2:8080`.
- Celery worker does not auto-reload: `docker compose restart celery_worker` after task code changes.
- Login payload: `{"app": "saving", "identifier": "<username or email>", "password": "..."}`.
- Account types are only bank/cash. No credit card accounts: card spending (manual or from card statement import)
  is an expense on the related bank account; balance = money available to spend. Card installments = installment plan.
- Accounts/categories referenced by transactions: account delete is PROTECTed (409, archive instead); category delete sets NULL.
- A test account `smoketest` / `smoke@example.com` (app `saving`) exists from the smoke test; delete it from the admin if unwanted.
