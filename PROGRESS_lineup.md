# PROGRESS: Line Up (`lineup`)

Phase and task tracking for the Line Up client (data-driven card ordering game). Update whenever a task is done or the plan changes.
Rules live in `CLAUDE.md` (Core Design Rule 8). Original brief (input only): `docs/BRIEF_lineup.md`.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo · Size: S / M / L (L = split before starting)

---

## ⏳ Waiting on user (pending commands)

```powershell
# 0.6 (dev PC): new requirement firebase-admin + new shared app `notifications` (no models, no migration)
docker compose up -d --build        # rebuild the backend image (web, celery_worker, celery_beat)
# phone: adb reverse tcp:8000 tcp:80 ; cd mobile_lineup ; flutter run --dart-define=API_URL=http://localhost:8000/api/v1
# app: Ana ekran -> Geliştirici araçları -> allow notifications -> "Reklam izle" (test ad -> "Ödül kazanıldı")
docker compose exec web python manage.py send_test_push lineup                   # app open: shown on the dev screen
docker compose exec web python manage.py send_test_push lineup --title "Arka plan" # app in background: system tray

# Server, later: copy backend/secrets/firebase-lineup.json by hand (never via git), then pull + up -d --build + migrate + bootstrap
```

---

## Phase 0: Foundation + plugin proof
Goal: `lineup` exists as a client, a guest can log in from a Flutter app on a real device, and the risky plugins (rewarded ad, FCM) are proven before game work.

- [x] **0.1** Docs (S): per-client `PROGRESS_<slug>.md` / `docs/FLOW_<slug>.md`, CLAUDE.md rules for Line Up, commit scopes.
- [x] **0.2** Register client (S) · after 0.1
  - `settings.CLIENT_APPS["lineup"] = "Line Up"`; `bootstrap` creates it; `legal_texts/lineup/` privacy + kvkk drafts.
  - Done when: `bootstrap` is idempotent and shows `lineup` in admin; `publish_legal_documents lineup` works.
- [x] **0.3** Guest accounts in shared `accounts` (M) · after 0.2 (migration 0005 applied on dev)
  - `ClientApp.allow_guests` (from `CLIENT_APPS` via bootstrap), `User.is_guest`, email unique per app only when set,
    `POST /api/v1/auth/guest/` {app, accepted_documents} → user + credentials (once) + JWT pair (throttle `guest` 10/hour),
    `is_guest` in `/auth/me/`, admin filters. Saving: email still required, guests refused (`guests_not_allowed`).
- [x] **0.4** Flutter toolchain (S, user): Flutter SDK, Android SDK, VS Code Dart/Flutter extensions, `flutter doctor` clean, phone in USB debugging.
  - Done: Flutter 3.50.1 at `C:\dev\flutter`, shares Flet's Android SDK (`C:\Users\anilc\Android\sdk`, API 34-37), licenses OK.
  - Honor VKJ-NX9: installs over wireless adb, but logcat is blocked → `flutter run` hangs after install (no hot reload).
    Dev loop = emulator; real-device checks with `flutter run --release` or another phone later.
  - [x] Emulator: `hello_test` runs and hot reload works (first install may time out on a slow first boot; re-run).
- [x] **0.5** `mobile_lineup/` skeleton (M) · after 0.3, 0.4 — checked on the Honor phone over USB (`adb reverse`):
  consent → guest → home, "Sunucu: ok"
  - Flutter 3.50 project, applicationId `tr.com.appmanager.lineup` (provisional, final in 5.0), label "Line Up".
    Packages: flutter_riverpod 3, go_router 18, dio 5, flutter_secure_storage 11, material_ui (Material moved out of
    the framework in Flutter 3.47: import `package:material_ui/material_ui.dart`, not `flutter/material.dart`).
  - `config.dart` (debug → `http://10.0.2.2`, release → production, `--dart-define=API_URL`); debug-only cleartext HTTP.
  - `ApiClient`: Bearer token, on 401 renew once (refresh → guest re-login) and repeat; Turkish `detail` → `ApiException`.
  - `SessionController` (AsyncNotifier): stored session → `/auth/me/` (pending texts → consent) else legal texts → guest.
    Router redirects follow it: `/` (loading/error + retry), `/consent`, `/home` (mode placeholders + server health).
  - Production check with `flutter run --release` after the server deploy (moved to 0.7).
- [~] **0.6** Plugin proof (M) · after 0.5 (no Play account needed) — code done, waiting on the device check above
  - Firebase project `lineup-53c97` (Analytics off); `google-services.json` + `backend/secrets/firebase-lineup.json` git-ignored
    (secrets also docker-ignored; the container reads them through the `./backend:/app` mount).
  - Backend: shared `notifications` app (`fcm.send(app, ...)`, a firebase_admin app per client slug), `send_test_push`.
  - Mobile: google-services Gradle plugin 4.6.0, firebase_core / firebase_messaging (token via `register()` +
    `onRegistered`; `getToken` is deprecated), google_mobile_ads with Google's TEST app id + rewarded test unit;
    debug-only "Geliştirici araçları" screen (`/home/dev`), subscribes to topic `lineup-dev`.
  - AdMob **test** rewarded ad shows and the reward callback fires.
  - Firebase project + `firebase_messaging` token; a management command (firebase-admin) sends a test push that arrives.
  - Done when: both work on a real device in a debug build.
- [ ] **0.7** Close the phase: `docs/FLOW_lineup.md` updated; push + server deploy (copy the Firebase key by hand);
  `flutter run --release` against https://appmanager.com.tr (guest + consent + "Sunucu: ok").

## Phase 1: Card pool + engine + Timeline (first playable)
- [ ] **1.1** `lineup_cards` models + admin (M)
  - `Attribute`, `CardType` (+ attribute schema), `Card` (`is_demo`, `external_key`, `extra`), `CardValue` (number | date + precision), `Tag`.
  - Admin: value inlines, filters (type/status/tag/popularity), bulk approve/reject; schema validation before approve.
  - Done when: a new type (e.g. "Futbolcu" with "transfer ücreti") is defined in admin only, no code change.
- [ ] **1.2** Demo seed `seed_lineup_demo` (S) · after 1.1: ~60 fake cards over 3 types (il: nüfus/yüzölçümü; olay: tarih; film: tarih), `--purge`.
- [ ] **1.3** Admin import (M/L, split: template+preview / confirm+upsert) · after 1.1
  - Per-type xlsx template generated from the schema → upload → dry-run preview with per-row errors → confirm →
    upsert by `(card_type, external_key)` into staging. `CardImport` record keeps the report; large files run in Celery.
- [ ] **1.4** Engine core + tests (M) · after 1.1
  - DTOs, comparison with precision + ties, seeded RNG, base generator (popularity threshold, min gap, category mix),
    `TimelineGenerator`, slot validation, lives (3), win (line reaches 10 cards), 10 s + 2 s timer check.
  - Done when: tests pass; same seed + pool → same deck.
- [ ] **1.5** `lineup_games` runs + API (M) · after 1.4
  - `Run` (mode, seed, params, frozen deck ids, lives, score, `dealt_at`, status), `Move` log; start / state / move / timeout.
    Row lock against double submit. Done when: API E2E; no unrevealed value ever appears in a response.
- [ ] **1.6a** Mobile Timeline: tap-a-gap placement, countdown, correct/wrong feedback (color + haptics), end screen (M) · after 1.5
- [ ] **1.6b** Mobile Timeline: drag & drop with auto-scroll, tested on a real device (M) · after 1.6a
- [ ] **1.7** "Hata bildir" on a card (support registry `lineup.card`) + mobile button (S)
- [ ] **1.8** `docs/FLOW_lineup.md` updated.

## Phase 2: Streak mode + energy
- [ ] **2.1** Engine `StreakGenerator` + tests: higher/lower, ties correct, 1 life, one continue per run (S/M)
- [ ] **2.2** Energy (S): lazy formula, spent on Timeline/Streak start; max / refill / new-player grace from env; tests.
- [ ] **2.3** API: start streak, move, energy on the home endpoint (S)
- [ ] **2.4** Mobile: Streak screen (drag up/down + buttons), energy indicator with "full at", out-of-energy dialog (ad/Pro placeholders) (M)
- [ ] **2.5** FLOW updated.

## Phase 3: Daily puzzle + share
- [ ] **3.1** Engine `DailyGenerator` (6 cards) + per-position attempt scoring + tests (S)
- [ ] **3.2** `DailyPuzzle` (unique date, Europe/Istanbul, frozen deck, created lazily), max 3 attempts, no energy, share text `🟩🟨🟥 – 2. deneme` (S/M)
- [ ] **3.3** Mobile: reorder screen, attempt feedback, result + `share_plus`, home status (M)
- [ ] **3.4** FLOW updated.

## Phase 4: Account linking + profile
- [ ] **4.1** Shared `accounts`: Google sign-in (server verifies the ID token; Google id per app), link to guest, login on a new device (M)
- [ ] **4.2** Profile/stats endpoint: best streak, wins, daily streak (S)
- [ ] **4.3** Mobile: profile, settings (Google link, legal texts, account freeze/deletion reused from accounts) (M)
- [ ] **4.4** FLOW updated.

## Phase 5: Monetization
- [ ] **5.0** (user + decision) Permanent package name, Play Console app, AdMob app + rewarded unit with SSV callback URL, RevenueCat project.
- [ ] **5.1** Shared `billing`: AdMob SSV endpoint (Google key signature check, idempotent by transaction id) → reward registry →
  lineup handler (+1 energy or one continue per run); daily ad cap (M)
- [ ] **5.2** Mobile: rewarded flows (custom data = server reward intent; grant only after SSV) (M)
- [ ] **5.3** RevenueCat webhook → `pro` entitlement per user → unlimited energy, ad-free continue, daily archive (M)
- [ ] **5.4** Mobile: Pro screen (`purchases_flutter`), restore (M)
- [ ] **5.5** UMP consent (EEA), legal texts updated for ads (S)
- [ ] **5.6** FLOW updated.

## Phase 6: Invite challenges + push
- [ ] **6.1** `lineup_social`: challenge (code, mode, frozen deck, creator result, expiry), accept (free) → compare (M)
- [ ] **6.2** App Links: `/.well-known/assetlinks.json` via nginx (list of all clients) + web fallback page for the invite link (M)
- [ ] **6.3** Shared `notifications`: device tokens, Celery FCM sends; push on challenge received / result (M)
- [ ] **6.4** Mobile: create/share, incoming list, result compare, deep links, push, local notifications (energy full, daily ready) (L, split)
- [ ] **6.5** FLOW updated.

## Phase 7: Real data pipeline (deliberately last)
- [ ] **7.1** Source adapter interface feeding the 1.3 import pipeline; Wikidata SPARQL adapter per card type (M/L)
- [ ] **7.2** Auto checks: missing / outlier / duplicate / no Turkish label / low popularity; popularity = sitelinks + trwiki page views (M)
- [ ] **7.3** Monthly refresh (beat); changed values go back to staging (S)
- [ ] **7.4** Target card counts per category + distribution report in admin (S)
- [ ] **7.5** Purge demo cards (S)

## Phase 8: Visual design (dedicated phase)
## Phase 9: Release
- Icon/splash, signed AAB, Play forms (audience 13+, data safety, ads), internal → closed test, metrics (D1/D7/D30, puzzle share rate, challenge accept rate).

## Later
- Live race (Django Channels): `web` moves to ASGI, which also affects Saving, so plan it separately.
- iOS.

---

## Notes / Decisions
- 2026-11-21: Name **Line Up**, slug `lineup`. Same repo, DB, Docker stack and home server as Saving; isolated by `ClientApp`.
- Mobile = Flutter (Flet lacks official rewarded ads, IAP and FCM support). Subscriptions: RevenueCat.
- Audience 13+. Package name decided at 5.0. Play developer account: handled by the user.
- Ties: equal at the coarser date precision (or equal numbers) → either order is correct.
- Timer: 10 s (+2 s grace) on Streak and Timeline, enforced by the server; none on the daily puzzle.
- Defaults to tune later: Timeline win = line reaches 10 cards (start card + 9), 3 lives; Streak 1 life + one ad
  continue per run; energy max 5, +1 every 25 min, no limit for new players' first days.
- Fake test data is fine until Phase 7, flagged `is_demo`.
