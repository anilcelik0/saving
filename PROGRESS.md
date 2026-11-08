# PROGRESS

Phase and task tracking. Update this file whenever a task is completed or the plan changes.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo

---

## ⏳ Waiting on user (pending commands)

```powershell
# Phase 2a: saving_budget models
docker compose exec web python manage.py makemigrations saving_budget
docker compose exec web python manage.py migrate
```

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
### 2a: Core budget (code done, waiting on migration + smoke test)
- [x] Models: Category, Account (bank/credit card/cash), Transaction, RecurringPayment (weekly/monthly/yearly, interval, installments), SavingGoal + GoalContribution (negative = withdrawal)
- [x] Shared helpers: `core.viewsets.OwnedModelViewSet`, `core.serializers.OwnedPrimaryKeyRelatedField`, ProtectedError → 409
- [x] Default categories seeded on saving user registration (signal)
- [x] CRUD APIs under `/api/v1/saving/budget/`: categories, accounts, transactions (filters), recurring-payments, goals (current_amount, progress_percent), goal-contributions
- [x] `recurring-payments/upcoming/?days=30` (incl. overdue), `recurring-payments/{id}/pay/` → expense transaction + next due date
- [~] Migrations (user) → API smoke test
- [ ] (Later) Payment reminder (Celery task + push notification)
- [ ] (Later) Recurring income (e.g. salary), "skip this period" action

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
- [ ] Monthly income/expense, category breakdown, savings progress, portfolio value

## Phase 5: Mobile (Flet, Android)
- [ ] Skeleton, API client, secure token storage
- [ ] Auto refresh: on 401 `token_not_valid` call `auth/refresh/` once (single-flight, since old refresh is blacklisted after rotation), retry request; go to login only if refresh fails. Also refresh on app start.
- [ ] Login/register screens, then screens per backend phase
- [ ] APK build

---

## Notes / Decisions
- No django-celery-beat: schedules live in code (`CELERY_BEAT_SCHEDULE`).
- No CORS package: Android native client does not need it.
- Local runs production-like (`DEBUG=False`); errors are visible in `docker compose logs web`.
- Android emulator reaches the host via `10.0.2.2:8080`.
- Celery worker does not auto-reload: `docker compose restart celery_worker` after task code changes.
- Login payload: `{"app": "saving", "identifier": "<username or email>", "password": "..."}`.
- Accounts/categories referenced by transactions: account delete is PROTECTed (409, archive instead); category delete sets NULL.
- A test account `smoketest` / `smoke@example.com` (app `saving`) exists from the smoke test; delete it from the admin if unwanted.
