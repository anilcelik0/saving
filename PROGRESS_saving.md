# PROGRESS

Phase and task tracking. Update this file whenever a task is completed or the plan changes.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo

---

## ⏳ Waiting on user (pending commands)

```powershell
# Demo user with ~6 months of data for looking at the UI (re-run = rebuild); login: demo / Demo-12345
docker compose exec web python manage.py seed_demo_data

# Two compose files (after the commit is pushed). Dev PC: nothing to do.
# Server (docs/DEPLOY.md section 0): FIRST edit the server .env:
#   add    COMPOSE_FILE=docker-compose.prod.yml
#   remove COMPOSE_PROFILES=tunnel (and --reload from GUNICORN_CMD_ARGS if present)
git pull; docker compose up -d --build; docker compose ps   # then open https://appmanager.com.tr/admin/

# Legal texts (done on dev PC; server after pull). The two values belong in .env (dev + server), not .env.example:
#   LEGAL_CONTROLLER_NAME=<ad soyad>   LEGAL_CONTACT_EMAIL=<e-posta>
# "Sorun bildir" (dev PC): new shared app `support` + texts v2 (bug reports section)
docker compose exec web python manage.py makemigrations support
docker compose exec web python manage.py migrate
docker compose restart celery_worker celery_beat   # new task: support.tasks.purge_issue_attachments
docker compose exec web python manage.py publish_legal_documents saving   # privacy/kvkk v2 -> users re-accept
# Server, after git pull: docker compose up -d --build; migrate; publish_legal_documents saving

# Account freeze / deletion (dev PC). Until migrate, the dev API fails on user queries (new User columns).
docker compose exec web python manage.py makemigrations accounts
docker compose exec web python manage.py migrate
docker compose restart celery_worker celery_beat   # new task: accounts.tasks.delete_scheduled_accounts
# permanent deletion right away (tests, or a KVKK request by e-mail):
#   docker compose exec web python manage.py delete_account saving <username or e-mail> --now

# Statement reader v2 (dev PC): new StatementImport fields check_status/check_message; worker runs the parser
docker compose exec web python manage.py makemigrations saving_budget
docker compose exec web python manage.py migrate
docker compose restart celery_worker

# Statement reader accuracy (2026-11-28). Dev PC: migration 0011 already applied; the worker runs the new engine
docker compose restart celery_worker
# Server, after git pull: docker compose up -d --build; docker compose exec web python manage.py migrate
# After every change in saving_budget/statements (samples in backend/statement_samples/, git-ignored):
docker compose exec web python manage.py check_statements            # --accept after checking the differences
# New sample from a real statement (copy it into backend/statement_samples/raw/ first, delete it afterwards):
docker compose exec web python manage.py make_statement_sample statement_samples/raw/<file> --review

# APK (uses https://appmanager.com.tr automatically)
cd mobile; New-Item -ItemType Directory -Force assets\fonts; Invoke-WebRequest "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf" -OutFile assets\fonts\Inter.ttf
start ms-settings:developers               # Developer Mode ON (Flutter plugins need symlinks)
.venv\Scripts\flet build apk
```
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

## Phase 2: saving_budget ✅
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

### 2b: Statement parsing ✅
- [x] `StatementImport` + `StatementLine` (preview) models; files in private storage (`/vol/private`, not served by nginx),
      deleted right after parsing; samples folder `docs/extre_example/` git-ignored (personal data)
- [x] `saving_budget/statements/`: `ParsedLine/ParsedStatement`, registry + auto-detect, utils (TR/US amounts, dates)
- [x] Parsers: VakıfBank account (PDF + XLSX), VakıfBank card (PDF), QNB card (PDF, broken-font cid fix),
      Garanti BBVA card (PDF — sample had only payments, purchase rows unverified)
- [x] Card rules: payment/summary rows dropped, refunds → income, earlier-period installments booked on cut-off date
- [x] Classification: skip card payment / own-account transfer / investment & deposit; keyword category suggestion
- [x] Dedupe key (bank ref or hash) on `Transaction.external_key`; pending-match suggestion (±7 days, installments: statement period)
- [x] API: `statements/` (multipart upload, poll, `lines/`, `confirm/`), `statement-lines/{id}/` (action/category/match)
- [x] Celery `parse_statement_task`; verified parsers on samples (card totals match statement: 15,166.39 / 5,328.93)
- [x] Mobile: More > Ekstreler (list, upload with account choice), preview (checkbox, edit action/category, confirm)
- [x] Migrations + rebuild (user); E2E: xlsx import (12 new / 1 rent match / 7 skipped), re-upload as pdf → duplicates,
      card import (23), garanti → failed message, txt → 400, files deleted after parse; mobile review/confirm headless test
- [x] `seed_default_categories` command (idempotent) — run for 10 existing saving users without categories
- [x] `docs/FLOW_saving.md` updated (statement import diagram)
- [x] **Generic reader** (`parsers/generic.py`, registered last): date-first + amount-last rows (TR/US amounts,
      n/m installments, trailing extras), account "amount balance description" layout, card/account by header hints,
      bank name detection, `is_generic` flag → mobile warning. Matches dedicated parsers on all 4 sample formats;
      Enpara card works through it (25 lines, total 13,647.32 = statement)
- [x] **cid font decoder** (`statements/cid.py`): learns cid→letter per PDF from common statement words
- [x] Migration for `is_generic` (user)
- [x] **Enpara card parser** (`parsers/enpara.py`); E2E upload → enpara/card, not generic, 25 lines imported
- [x] Garanti card parser verified with a purchase sample (11 lines, 39,286.19 = statement): "bosluk" filler,
      bonus column, "x12=... 11.Taksit" installments, original-currency column
- [x] Generic reader: card "bonus amount" → last amount, filler words, installment plans; equals dedicated parsers on all PDFs
- [x] **Category never empty**: new defaults (Online Alışveriş, Ev & Elektronik, Kişisel Bakım, Para Transferi,
      Nakit Çekim, Banka Masrafı, Gelen Transfer, İade); rules: merchant → purpose → channel (ATM/FAST/fees)
      → online signals → card refund → fallback Diğer Gider/Gelir; seeded for 14 existing saving users
- [x] **Category learning**: `MerchantCategoryRule` (user, kind, merchant_key → category, hits); `merchant_key()` strips
      gateways/branch codes ("IYZICO/HEPSIBURADA.C" → hepsiburada, "BİM P226" → bim, "Uber Eats" → uber eats).
      Learned on category change (preview line or transaction edit); applied before built-in rules; same-merchant
      preview lines updated instantly; API `category-rules/` (list/delete); mobile More > Öğrenilen kategoriler
- [x] **Refunds**: Transaction status `cancelled` (history only; excluded from balance/summary). Card refund with same
      amount + same merchant → action `refund` cancels the purchase (same statement or paid within 90 days);
      otherwise imported as income "İade". Manual `transactions/{id}/cancel|restore/` (also "skip this occurrence")
- [x] Migration (user); E2E: QNB Steam refund cancels purchase in same statement, learned rule updates 7 same-merchant
      lines and applies to next statement, tx edit learns, cancel/restore balance. (Refund of an earlier-imported purchase: not covered by samples)
- [x] **Card statement cycles** (decision: no estimates, no interim uploads — statements only):
      `Account.statement_day` (1-31, auto-filled from first card statement), `Transaction.is_card` (card statement
      lines, matched pendings, manual "Kredi kartıyla"). Lists show real dates; monthly summary counts card
      transactions by their account's cycle (day 15 → Jan 16–Feb 15 = February), non-card by calendar month,
      each account evaluated separately (`services.month_scope`, `card_cycle`); summary returns `card_cycles`
- [x] Migration 0005 (user). Note: card transactions imported before this change are not flagged `is_card`
- [x] **History-only upload**: checkbox "Bu ekstre bakiyeden düşülmesin" (default off) → `exclude_from_balance`,
      transactions `in_balance=False`: counted in summaries/reports, excluded from balances, overdue, projection;
      no pending-match suggestions
- [x] **Account-based activity**: `activity/?month=` (non-card movements one by one + one row per card statement cycle
      per account, same scope as summary), `activity/upcoming/` (card pendings grouped per cycle),
      `transactions/bulk-status/` (mark a cycle paid/unpaid); mobile Hareketler: month-navigated history,
      card cycle rows → detail view with "Tümünü ödendi / ödenmedi"
- [x] Hareketler = month view only (pending section removed; this month's pendings inline with quick pay;
      navigation up to +1 month). More > **Otomatik ödemelerim** (`series/` API): recurring/installment plans with next
      occurrence; edit via next occurrence (scope dialog), + adds a recurring payment
- [x] **Card names**: `Account.card_name` auto-filled from the bank name only ("Enpara Kredi Kartı", editable);
      shown on card cycle rows and card transactions. **Decision: no card numbers are read from statements.**
      `backfill_card_flags` command (flags older card imports) kept for reference
- [x] **Statement data privacy**: file deleted right after parsing (+ nightly cleanup of never-parsed files > 1h);
      raw statement text cleared on confirm; preview checkbox "Aktardıktan sonra ekstre bilgilerini sil" (default on)
      deletes statement record + lines after import (transactions stay); delete button on statement list.
      Re-upload dedupe works without statement records (transaction keys; refunds detected via cancelled purchase)
- [x] `reset_budget_data --yes`: wipes all budget data (keeps users), re-seeds default categories
- [x] Migration + data reset (user) → full E2E: 18/19 OK. Found: purchases on the cut-off day billed by the bank
      in the NEXT statement (Enpara 15.01 rows in 15.02 statement) fell into the previous cycle
- [x] Fix: `Transaction.cycle_end` = statement cut-off for imported card rows; cycle grouping/summary/bulk use it
      (`card_cycle_q`), manual card rows still use the statement-day rule; cycle totals now equal bank statements
- [x] Migration for `cycle_end` + data reset (user) → final E2E 19/19 OK (Enpara cycle = statement: 25 / 13.647,32) → Phase 2 closed
- **Adding a bank:** user drops samples into `docs/extre_example/` → add `parsers/<bank>.py` (`@register`, import it in
  `parsers/__init__.py` BEFORE `generic`), add label to `BANK_LABELS`, compare totals with the statement summary
- [ ] (Later) Remember user's category choices per merchant; Garanti purchase rows sample; generic XLSX reader

## Phase 3: saving_invest ✅
Decisions (2026-11-09): USD/EUR from TCMB `today.xml` (ForexBuying/ForexSelling); gold/silver from Altınkaynak
`static.altinkaynak.com/public/Gold` (GA, C, Y, T, AG_T; TR number format). Assets: USD, EUR, gram/çeyrek/yarım/tam
gold, gram silver.
Revised: no selling / realized P/L. Only purchases + "reduce quantity" (optionally add the TRY received to an account
as income). Purchases and deposit openings can optionally be deducted from a budget account (expense, category
"Yatırım"). Time deposits: user enters rate, maturity date and maturity amount (default = simple interest net of 17.5% withholding, `DEPOSIT_WITHHOLDING_RATE`);
at maturity the user renews (new deposit, principal = maturity amount) or closes (amount optionally to an account).
### 3a: Backend
- [x] Models: `Asset` (shared catalog synced from `catalog.py`), `AssetPrice` (one row per asset/day, buy/sell),
      `Trade` (buy/reduce, quantity, unit price, proceeds, account, budget_entry), `Deposit` (rate, maturity,
      status active/renewed/closed, previous, open/close budget entries)
- [x] Provider adapters (`providers/`: `tcmb`, `altinkaynak`, registry `PROVIDERS`); URLs overridable via env
- [x] `fetch_prices()` + celery-beat `fetch_daily_prices` 17:00 (retry 3× every 30 min) + `fetch_prices` command
- [x] Portfolio: average cost, value at latest buy price, gain %, day change %; active deposits valued with linearly
      accrued interest; totals
- [x] Holding never below zero on create/edit/delete (timeline replay; same-day buys first), per-user write lock
- [x] Budget mirror: `saving_budget.services.sync_linked_entry` (source `investment`, category "Yatırım" auto-created)
- [x] API `/api/v1/saving/invest/`: `assets/` (+`{code}/history/?days=`), `trades/` (?asset=&side=), `deposits/`
      (?status=; `{id}/close/`, `{id}/reopen/`, `{id}/renew/`), `portfolio/`
- [x] Migration + first fetch (user) → API E2E 21/21 OK (first user run: TCMB fetch failed once; retry/rerun fine)
### 3b: Mobile
- [x] Yatırımlar tab (4th bottom tab): total value, holdings (value, gain %), active deposits, current prices
- [x] Asset view: holding, average cost, last-30-day range, purchases/reductions list; trade form (asset picker,
      price prefilled with current sell price, optional account; reduction: optional TRY + account)
- [x] Deposit form / detail (edit, renew, close, reopen, delete) / history; `services/invest_service.py`
- [x] Screen check against live API with a stub page (forms → API → balances) OK; FLOW_saving.md section 9

## Phase 4: saving_reports ✅
Decisions (2026-11-10): all four reports; period = end month + 1/3/6/12 months, same month scope as the summary
(card rows by statement cycle, cancelled excluded). Read-only app, no models.
- [x] `reports/categories/` (kind, month, months): amount, share, count, change vs. previous equal period;
      `reports/categories/transactions/` drill-down (category id or `none`)
- [x] `reports/trend/` (months 1-24, default 12): income, expense, net, investment in/out, saving, saving rate;
      averages over months that have data
- [x] `reports/wealth/`: month-end (today for current month) cash (paid in-balance movements up to that day),
      holdings at that day's latest buy price (cost when no price yet -> `priced: false`), deposits with accrued
      interest, net worth, investment gain
- [x] API E2E 17/17 (hand-computed expectations); mobile "Diğer > Raporlar" (4 screens + drill-down), checked
      against live API with stub page
- Known: net worth uses account opening balance at every month (no opening date), so long-range % change can be large

## Phase 5: Mobile finalization 🔄
Design decisions (2026-11-10): direction A "calm & airy" (canvas: https://claude.ai/artifact/CjZ1b3xTJdqjCq6tpgVuA1),
light/dark following the phone, Inter, teal accent; one central + button with all add actions; home shows balance +
projection, spending ring, 6-month income/expense bars, net worth line, upcoming payments. Charts drawn with
`flet.canvas`/containers (no extra package).
- [x] Step 1: `screens/theme.py` (light/dark color schemes, card/section/stat, donut, grouped bars, line chart),
      shell with bottom bar + central + (add menu: entry, statement upload, gold/currency buy, deposit, account),
      new Özet screen; checked against live API with stub page
- [x] Step 2: Hareketler (badged rows in cards, month chip), Yatırımlar (value card, allocation ring, holdings/
      deposits/prices with badges), Diğer (profile card, grouped menu), sub-screens and reports (ring, bars, line
      charts) restyled; per-tab FABs removed; 15 screens opened against live API with stub page, no errors
- [x] Fix: + sheet tiles had vertical stretch inside a content-sized bottom sheet (unbounded height) -> fixed
      tile height, scrollable sheet
- [x] App settings (Diğer > Uygulama ayarları, stored on the device: `services/settings_store.py`): theme
      system/light/dark, default account for new entries, upcoming payments window, start tab, hide amounts on
      Özet (also eye toggle on the balance card); version + server shown
- [x] Demo data: `saving_invest` command `seed_demo_data` (user `demo` / `Demo-12345`, ~6 months: 3 accounts,
      recurring + installment + card spending, overdue bill, trades incl. reduction, closed/matured/active deposits);
      re-run rebuilds only that user
- [x] Data-entry forms redesign, chosen style "Form 2 · big amount + chips" (canvas, 2nd row):
  - [x] `screens/form_kit.py`: big amount, Chips, Segmented, CategoryGrid (recently used first, stored on the
        device; then common defaults; 7 + "Tümü"), DateChips (Bugün/Dün/Tarih seç), Collapsible, QuickForm
        (close · center · delete, sticky action button with the amount); category icons/colors by name in theme.py
  - [x] Gelir/gider entry form (new + edit; card spending is an account chip "Enpara kartı"; repeat/installment/
        note in "Tekrar, taksit, not"); checked against live API with stub page
  - [x] Investment forms: trade (asset chips, big quantity, live total, account chips with "no account"),
        deposit open/renew (term chips 32/46/92/181 days + date; maturity amount + note collapsed), close
  - [x] Account (card section toggled by "Kredi kartı var"), category (icon + color picker, stored in the existing
        `icon`/`color` fields; list shows the badges), profile, pay dialog; old `form_view`/`DateInput`/
        `money_field`/`int_field` removed from ui.py; all forms saved against live API with stub page
- [x] Entry form: description shown as a prominent "İsim" field under the amount (API messages say "isim")
- [x] App tour (`screens/onboarding.py`): 8 swipeable pages with mini illustrations (welcome, accounts, + menu,
      quick entry, statement upload + privacy, summary/activity, investments, settings); shown once per user on
      this device (`onboarded` setting), Atla/Geri/İleri; with no accounts the last page offers "İlk hesabımı ekle";
      replay from Diğer > Uygulama turu; checked with stub page
- [x] Step 3: secure token storage: `flet-secure-storage` (Android Keystore) in `services/token_store.py`;
      tokens from older SharedPreferences moved once and removed; falls back to SharedPreferences when the
      extension is missing/not answering (3 s probe, e.g. desktop `flet run`; logged as a warning). Hakkında
      shows only the version (server URL and token status removed on request). Real check on the Android build
      (step 4)
- [x] Cloudflare Tunnel: `cloudflared` service (token from `.env`) -> nginx:80;
      nginx keeps CF's `X-Forwarded-Proto` (Django sees https) and passes `CF-Connecting-IP` as `X-Real-IP`
- [x] Dev/prod split (2026-11-16, simplified on request): two self-contained files. `docker-compose.yml` =
      development (unchanged services, no tunnel); `docker-compose.prod.yml` = same services + `cloudflared`
      (always on, token required), chosen on the server by `COMPOSE_FILE=docker-compose.prod.yml` in its `.env`.
      `COMPOSE_PROFILES` no longer used. Keep shared services identical in both files
  - [ ] Apply on the server: `.env` edit + `git pull` + `docker compose up -d --build`
- [~] Step 4: production + Android build
  - [x] Decisions (2026-11-15): server = home PC (Windows 11) behind Cloudflare Tunnel, API on
        https://appmanager.com.tr/api/v1; code via GitHub private repo; development stays local
  - [x] Mobile server choice (`mobile/config.py`): built app (`FLET_PLATFORM` set) -> production HTTPS; `flet run`
        (also `--android`, Python runs on the PC) -> http://localhost or git-ignored `local_config.py`, which is
        excluded from builds (`[tool.flet.app] exclude`); cleartext HTTP permission removed
  - [x] Django: `DJANGO_SECURE_COOKIES`, `DJANGO_HSTS_SECONDS` env flags for the server; port 80 for nginx
  - [x] Inter loaded from `assets/fonts/Inter.ttf` when present (`ft.run(..., assets_dir="assets")`), else URL
  - [x] `docs/DEPLOY.md`: repo, server prep (auto start, no sleep), `.env` values, first run, Cloudflare, update,
        backup/restore (pg_dump via `docker compose cp`; PowerShell `>` corrupts binary)
  - [x] GitHub repo (`origin` = github.com/anilcelik0/saving), server installed by the user, site up
  - [ ] Build APK (Developer Mode on, Android SDK 36), install, check on the phone (login, forms, statement upload,
        session kept after restart)
  - [ ] Play Store: developer account registration pending; then `flet build aab`, signing key, store listing

## Phase 6: Google Play readiness 🔄
Decisions (2026-11-16): package `tr.com.appmanager.saving`; personal developer account (closed test: 12 testers ×
14 days); data controller = the user's name + personal e-mail (from `.env`, approved for publishing); deletion =
request -> 30 days locked (login offers cancel) -> Celery deletes everything; deactivation = user freezes, login
reopens.
- [x] Package name: `[tool.flet] bundle_id = "tr.com.appmanager.saving"`, org `tr.com.appmanager`
- [x] App name (2026-11-28): **Bütçe Defteri** (store title "Bütçe Defteri: Harcama Takibi"; "Hesap Kitap" dropped,
      several apps use it; no Play app or trademark found under "Bütçe Defteri", descriptive so weak as a trademark).
      Shown in `product`, page title, login, onboarding; `CLIENT_APPS["saving"]["name"]` (shared settings, Line Up
      unchanged) → `ClientApp.name` → legal texts' `{{app}}` (filled when read, no new version). Slug, package and
      internal names stay `saving`. Pending: `manage.py bootstrap` on dev and server to update the DB name
- [x] Play Console declarations: `docs/PLAY_STORE.md` (privacy URL, app access, ads, IARC, audience 18+, financial
      features, data safety table, closed test steps, legal notes: KVKK md. 9 Cloudflare, VERBİS)
- [x] Legal texts + consents (shared `accounts` app); live check 30/30 (API: lists, Markdown body, web pages,
      register without/partial/full consent, consents GET/POST, login payload; stub UI: register checkboxes, reader,
      gate disabled until all checked, enter_app -> gate, settings screen). Fix: consent dates sent in local time
  - [x] `LegalDocument` (per app/kind, auto version, immutable once published, Markdown + placeholders
        `{{controller}}`/`{{email}}` from `LEGAL_CONTROLLER_NAME`/`LEGAL_CONTACT_EMAIL`), `LegalAcceptance`
        (user, document, time, IP via X-Real-IP, user agent)
  - [x] API: `GET legal/<app>/`, `GET legal/<app>/<kind>/` (public), `GET/POST auth/consents/`; register requires
        `accepted_documents` (all current required docs); `pending_legal` in user payload (login/register/me)
  - [x] Public pages `/legal/<app>/<kind>/` (Google Play privacy URL); admin: drafts editable, publish / new
        version actions, read-only acceptance log; `publish_legal_documents <app>` from `legal_texts/<app>/*.md`
  - [x] Texts: `legal_texts/saving/privacy.md`, `kvkk.md` (actual processing: no card numbers, statement files
        deleted after parsing, device-only settings, Cloudflare transit, 30-day deletion, KVKK md. 11 rights)
  - [x] Mobile: register checkboxes ("Okudum, kabul ediyorum" / KVKK "Okudum, bilgilendirildim") with reader;
        gate before the app when `pending_legal` (new version); Diğer > Gizlilik ve KVKK (accepted version/date);
        legal links on login; built app never downloads the font (system font if not bundled)
- [~] "Sorun bildir" (testing phase; waiting on the user's migration + restart, then live check)
  - [x] Shared app `support`: `IssueReport` (category bug/statement/suggestion/other, message, context JSON,
        related_type/id + snapshot, status new/in_progress/resolved/closed, response shown to the user),
        `IssueAttachment` (private storage, source upload/statement, deleted_at; file removed on row delete)
  - [x] `support.registry`: client apps register snapshots; `saving_budget` registers "saving.statement" (bank,
        parser, status, error, period, line counts by action; no file content or line texts)
  - [x] API `support/issues/` GET own / POST multipart (`attachments` ≤3, `statement_file`, 10 MB each,
        pdf/xlsx/xls/csv/images/txt, consent required with files, throttle 30/hour); admin: status/response,
        snapshot + context view, staff-only attachment download; nightly `purge_issue_attachments` (resolved/
        closed or older than 30 days)
  - [x] Mobile: bug icon in the home header (all tabs), "Bildir" on every error toast (form opens with the error),
        Diğer > Destek (Sorun bildir, Bildirimlerim with status/response), statement preview: icon + "Okumada bir
        sorun mu var? Bildir" (failed: "Bu ekstreyi bize bildirin"); statements uploaded in this session stay in
        device memory (last 3, cleared on logout) and are attached with consent, otherwise the user can pick the
        file again; technical info shown before sending
  - [x] Texts v2: privacy/kvkk sections for bug reports (data, purpose, 30-day attachment retention);
        PLAY_STORE.md data safety rows (user-generated content, app performance data, files)
  - [ ] Live check (`support_check.py` in scratchpad) after migration
- [x] Account freeze + deletion
  - [x] `User.account_status` active/deactivated/deletion_pending + `status_changed_at`, `delete_after`; login
        still works (client shows reopen / cancel); `AppPermission` refuses client APIs for non-active accounts
        (403 `account_inactive`); auth/support endpoints keep working
  - [x] `accounts.lifecycle`: deactivate, request_deletion (+30 days, `ACCOUNT_DELETION_GRACE_DAYS`), reactivate,
        delete_account (registered cleanups first: saving_budget removes Transaction/Series because of PROTECT to
        Account, leftover statement files; then the user row cascades); every change revokes all refresh tokens
  - [x] API `auth/account/deactivate|delete/` (password, throttled), `auth/account/reactivate/`; user payload has
        `account_status`, `delete_after`; nightly `delete_scheduled_accounts` (02:15)
  - [x] Web page `/account/delete/<app>/` (Google Play URL; credentials + confirmation, 10 failed tries / 15 min
        per IP); shared public template; admin: status columns/filter, actions "Silme talebi oluştur" and
        "HEMEN kalıcı sil" (the standard delete page is blocked by PROTECT); `delete_account <app> <user> [--now]`
  - [x] Mobile: Diğer > Hesap (Hesabı dondur / Hesabı sil: points, password, confirmation, red button) -> signed out
        with a message; status screen after login (reopen / cancel deletion) before the consent gate
  - [x] `core.exceptions`: custom error codes reach the client (`{"detail", "code": "account_inactive"}`)
  - [x] Live check 27/27 (API, web page, mobile stub) + permanent deletion of a user with transactions, recurring
        series, trade and report attachment via `delete_account --now`: 3/3 (login gone, username free, no data)
- [ ] App icon + splash, version/build number, signed AAB, target API 36 check, store listing, closed test (paused 2026-11-16: back to statement reading)

- [x] `manage.py bootstrap` (accounts, idempotent, run after every deploy): client apps from `settings.CLIENT_APPS`
      + `publish_legal_documents` per app. DEPLOY.md uses it

- [x] Account form (2026-11-17): "Kart yok / Kredi kartı var" toggle and card name field removed; a card always belongs
      to a bank account, so bank accounts just have an optional "Kredi kartı ekstre kesim günü" (hidden for cash).
      Existing card names are kept (PATCH), lists fall back to "<hesap> kartı". Checked 5/5 against live API

- [x] Toasts are floating SnackBars (above the bottom bar and the + button instead of pushing it up)
- [x] Every toast closes itself after 5 s, error toasts with "Bildir" too (`persist=False`; Flutter keeps snack bars
      with an action open by default) (2026-11-19)
- [x] Screens stay in sync (2026-11-19): `ApiClient.on_change` fires after every successful write (not GET, not
      auth/); `AppState.data_changed` waits 0.4 s (one refresh per burst of requests), reloads accounts/categories
      if they changed, then refreshes every open screen in the stack (screens link themselves: `view.data = self`)
      and the current home tab. Forms have no refresh, so typed input is never lost; one failing screen doesn't
      stop the others
- [x] Fix: picked dates were one day early (2026-11-19). Flet carries datetimes as UTC, so the chosen day's local
      midnight (UTC+3) arrived as the previous day 21:00 and `.date()` took that day -> a payment due tomorrow
      became today and auto-pay marked it paid at once. `form_kit.picked_day` (all DateChips) fixes it.
      Backend: editing date / auto-pay re-applies the auto-pay rule (`sync_auto_pay_status`: due -> paid on its
      date, moved to the future -> pending)
- [x] Pending auto-pay rows also show the quick "Öde" / "Alındı" button (pay before the due day)
- [x] Archive only offered when deleting: "Arşivlendi" switches removed from account/category forms; the delete icon
      opens Sil / Arşivle (Arşivden çıkar) / Vazgeç with a short explanation; deleting an account with records shows
      the 409 message. Backend: archive filter only on list actions (archived rows reachable by id). Checked 8/8
- [x] Fix (regression from 53837d0): `core.exceptions` crashed on Django Http404 (no `.detail`) -> every 404 was a
      500; now 404 again
- [x] Notch / camera cutout (2026-11-19): views without an AppBar (every QuickForm incl. payment detail, login) slid
      under the status bar, top buttons unreachable. `router.safe_area` wraps every pushed/reset view in a SafeArea
      (keeps the view's alignment/spacing; views already starting with a SafeArea untouched) -> covers future views
- [x] Delete a card statement cycle (2026-11-19): Hareketler -> Ekstre row -> trash icon -> confirm -> all card
      transactions of that account cycle deleted (`POST transactions/delete-cycle/`, same cycle rule as bulk-status,
      investment mirrors kept). Re-importing the statement afterwards works (dedupe keys are gone with the rows)
- [x] Issue reports pass (2026-11-28), statuses set in the dev DB:
  - "Vade otomatik seçilince ilk vadesi gelmese de ödeniyor": already fixed on 2026-11-19 (picked_day); re-checked
    9/9 in a rolled-back shell run (recurring / installment / single entry due tomorrow stay pending, due today ->
    paid, daily task on the due day, moved to the future -> pending) -> resolved
  - Hint text disappears on focus, comes back on blur (`form_kit.hide_hint_on_focus`: big_amount, inline_text,
    plain_input, entry description, report message) -> resolved
  - Ready names for recurring / installment entries (Kira, Aidat, Elektrik, Su, Doğalgaz, İnternet, Telefon,
    Netflix, Spotify, Kredi taksiti; income: Maaş, Kira geliri): a tap fills the name and selects the matching
    default category -> resolved
  - Back button could not close "Ekstre yükle" opened from the + menu: the dialog opened while the sheet was still
    closing; the chosen tile's action now runs on the sheet's `on_dismiss` -> resolved (check on the device)
  - "Kategori dağılımında gelir listelenmiyor": closed (not planned for now)
  - [ ] Check on the device (Android build), then set the same statuses on the production DB (admin)

## Statement reader v2: one general engine ✅
Why (2026-11-16): VakıfBank switched its card statement from US to Turkish number format (+ points column,
"Son Taksit") and the regex parser read 0 rows; per-bank regexes break on small layout changes.
- [x] `statements/` rewritten, per-bank parsers removed: `layout.py` (words + positions -> lines; date rows; amount
      columns from right/left/center alignment clusters; roles from header phrases), `tokens.py` (TR/US amounts with
      +/- markers, dates incl. "05 Ekim 2026", installment notes 2/6, 3. Taksit, AxN=T, 2x1.136,50, Son Taksit),
      `profiles.py` (bank from the non-row text, Enpara before QNB; card vs account by hints), `engine.py` (card:
      purchase sign from payment rows or the total; payments kept as `card_payment` lines; summary rows -> previous
      balance; installment dates; account: amount/debit/credit, sign from running balance if unsigned, wrapped
      description lines, FAST/EFT cleanup, ref no; Excel by header keywords; holder name)
- [x] Self-check on every statement: card previous + rows = debt, account running balance; `check_status`/`message`
      stored on StatementImport, shown on the preview (✓ / ⚠ with the difference + "bize bildirin"), flagged in the
      list, included in issue-report snapshots
- [x] Duplicate guard also by date + amount + kind of earlier imports (descriptions may change with the reader)
- [x] Checked on all 9 samples (docs/extre_example, never committed): all read and verified against the statement
      totals (before: 3 failed); vs. old output: account PDF/Excel, Enpara, QNB identical; differences are fixes
      (VakıfBank "kalan 2" was points, "2. taksit" -> 2/3, Garanti period from previous cut-off). Also verified with
      header recognition disabled (unknown-bank simulation): all 8 PDFs read and verified
- [x] Live check 8/8: November card statement uploaded -> ready, check ok (29.338,38), 32 lines, payment
      skipped as card_payment, installments 1/3 + 3/3, confirm, re-upload -> 31 duplicate + 1 card_payment;
      test data removed, sample copies deleted from the container

## Statement reader accuracy ✅ (2026-11-28)
Why: the Yapı Kredi statement read every row but failed the self-check (previous balance label unknown, the
"Kalan Tutar/Taksit" column unread, restructured-loan rows dated 2025). Goal: measure first, then improve.
- [x] Sample set + regression check: `statements/samples.py`, commands `make_statement_sample` (engine input with
      names / addresses (block under the addressee, address words, 81 provinces) / card, IBAN, customer, TC, phone
      numbers / e-mails masked; positions, amounts, dates, installment notes, labels and bank names kept; verifies the
      fixture reads exactly like the original) and `check_statements` (every fixture vs `<name>.expected.json`,
      `--accept`). 10 samples (VakıfBank account PDF + XLSX, VakıfBank card ×2, Enpara, Garanti ×3, QNB, Yapı Kredi),
      all 10 read like the originals; masked text reviewed by eye. Baseline stored before any engine change
- [x] Engine input split from files (`layout.extract_pages` / `engine.read_table` -> `parse_pdf_pages` /
      `parse_table`, `registry.read_input` / `parse_input`), so fixtures and files take the same path
- [x] `vocabulary.py`: every label word in one place (table header roles, summary roles + ignore list, row words,
      date / holder / balance patterns). Header words drop a glued "(TL)"; "Kalan Tutar/Taksit" = installment column
- [x] `summary.py`: card summary read without bank code: "label : amount" (amount may be right-aligned far away),
      grids / equations (labels on 1-4 lines above the amounts, matched per heading by position; running text and
      date lines stop the label search), table summary rows. `readings()` keeps combinations that agree with
      themselves (previous + charges + cash + fees - credits = debt); all 8 card samples give a full reading
- [x] `card.py`: undated lines under a row -> detail text ("N / M taksidi" read), breakdown (first lines summing to
      the row amount: Anapara + Faiz + BSMV + KKDF) or orphans (rows whose date line is missing). Every
      interpretation (purchase sign × orphans none / all / single × summary readings) is evaluated; the one with
      the most passed checks wins, the most likely on a tie. Checks: balance, charges, credits (refunds may be netted)
- [x] Line flags (`ParsedLine.flags` -> `StatementLine.flags`): installment_date (info), old_date (non-installment row
      > 45 days before the period -> cut-off date), date_outside, from_detail, suspect (difference = line amount),
      suspect_sign (difference = 2 × line amount), balance_break (account row where the running balance breaks).
      Account check also compares the printed closing balance. Messages name the difference and the flagged lines
- [x] Yapı Kredi: ok (76,35 debt, 10.225,71 charges, 20.298,72 credits), installments 20/40 and "kalan 20", old
      dates on the cut-off; other 9 samples: same dates/amounts, now with charges/credits checks
- [x] Fault injection (in memory): a row losing its date is recovered (from_detail, check ok); dropped row -> mismatch
      with the difference; flipped sign -> that row flagged suspect_sign; account amount misread / row missing -> the
      row flagged balance_break
- [x] Reading quality: `StatementReadLog` (anonymous: bank, type, file type, engine version, checks, line / flagged
      counts; on confirm: lines included/excluded differently than suggested + categories changed; outlives the
      statement record and account deletion, holds no personal data). `StatementLine.suggested_action/category`,
      `StatementImport.check_details`, migration 0011. Admin: check_status column/filter, line flags, "Okuma
      kalitesi" page (per bank / type / file type, period and engine version filters, problems first)
- [x] Mobile preview: per-check list when something is off, line notes (⚠ warn / info), "Yalnızca kontrol gereken
      satırlar" switch, Excel hint for PDFs that did not verify
- [x] Live check 14/14 (rolled back): upload -> ready/ok, 3 checks, flags, suggestions, API fields, review counted on
      confirm, log kept after statement delete, failed read logged, admin pages; no files left
- [ ] Privacy text (decision): mention anonymous reading statistics; using statements sent with "Sorun bildir" as
      masked samples needs its own sentence (the report consent says "inceleme için")
- [ ] OCR for scanned PDFs (later, if such statements appear: PaddleOCR words + positions into the same engine)

---

## Notes / Decisions
- No django-celery-beat: schedules live in code (`CELERY_BEAT_SCHEDULE`).
- No CORS package: Android native client does not need it.
- Both environments run with `DEBUG=False`; errors are visible in `docker compose logs web`.
- Production server is updated only from GitHub (`git pull` + `docker compose up -d --build`); never edit code there.
- Celery worker does not auto-reload: `docker compose restart celery_worker` after task code changes.
- Login payload: `{"app": "saving", "identifier": "<username or email>", "password": "..."}`.
- Account types are only bank/cash. No credit card accounts: card spending (manual or from card statement import)
  is an expense on the related bank account; balance = money available to spend. Card installments = installment plan.
- Accounts/categories referenced by transactions: account delete is PROTECTed (409, archive instead); category delete sets NULL.
- A test account `smoketest` / `smoke@example.com` (app `saving`) exists from the smoke test; delete it from the admin if unwanted.
