# PROGRESS: Line Up (`lineup`)

Phase and task tracking for the Line Up client (data-driven card ordering game). Update whenever a task is done or the plan changes.
Rules live in `CLAUDE.md` (Core Design Rule 8). Original brief (input only): `docs/BRIEF_lineup.md`.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo · Size: S / M / L (L = split before starting)

---

## ⏳ Waiting on user (pending commands)

```powershell
# Phase 4 device check: restart the backend (accounts + lineup code; gunicorn does not auto-reload)
docker compose restart web
#  - Home: profile icon (top right); daily tile shows "🔥 N gün" once you solved a puzzle
#  - Profil: stats (daily distribution, streaks, Timeline/Seri), legal texts open
#  - "Hesabını kaydet": email + password (+ optional username) -> profile shows the email, progress unchanged
#  - "Çıkış yap" -> login screen (email filled in) -> log in -> same progress
#  - new-device test without a 2nd phone: login screen "Misafir olarak yeni başla" -> consent -> new guest;
#    Profil > "Kayıtlı hesabınla giriş yap" -> your progress is back
#  - "Hesabı dondur" (password) -> login -> "Hesabın dondurulmuş" -> "Yeniden aç"
#  - "Hesabı sil": try it on a throwaway guest only (deleted for good after the grace period); logging in to a
#    registered account during the grace period offers "Yeniden aç" (cancels the deletion)
#  - Bulmaca: no 🚩 while playing, only on the result list
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
  - Honor VKJ-NX9 (wireless adb): logcat was blocked → `flutter run` hung after install. Fixed by enabling logs on the
    phone; hot reload + logs work. Keep "Select debug app" = none ("Waiting for debugger" otherwise).
  - Device → dev backend: `tool/adb_reverse.ps1` (device localhost:8000 → PC port 80), lost on every reconnect;
    VS Code F5 "Line Up (dev backend)" runs it first (local `.vscode/`, git-ignored).
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
  - Production check with `flutter run --release` after the server deploy (Phase 9).
- [x] **0.6** Plugin proof (M) · after 0.5 — checked on the Honor phone: rewarded test ad (reward callback) and
  `send_test_push lineup` (foreground on the dev screen + background in the system tray)
  - Firebase project `lineup-53c97` (Analytics off); `google-services.json` + `backend/secrets/firebase-lineup.json` git-ignored
    (secrets also docker-ignored; the container reads them through the `./backend:/app` mount).
  - Backend: shared `notifications` app (`fcm.send(app, ...)`, a firebase_admin app per client slug), `send_test_push`.
  - Mobile: google-services Gradle plugin 4.6.0, firebase_core / firebase_messaging (token via `register()` +
    `onRegistered`; `getToken` is deprecated), google_mobile_ads with Google's TEST app id + rewarded test unit;
    debug-only "Geliştirici araçları" screen (`/home/dev`), subscribes to topic `lineup-dev`.
  - AdMob **test** rewarded ad shows and the reward callback fires.
  - Firebase project + `firebase_messaging` token; a management command (firebase-admin) sends a test push that arrives.
  - Done when: both work on a real device in a debug build.
- [x] **0.7** Close the phase: `docs/FLOW_lineup.md` updated, pushed. Server deploy moved to the end (Phase 9, by request).
- Phase 0 done 2026-11-21. FCM note: `register()`/`onRegistered` needs manifest meta-data
  `firebase_messaging_installation_id_enabled=true`; the dev backend image must be rebuilt after requirement changes.

## Phase 1: Card pool + engine + Timeline (first playable)
- [x] **1.1** `lineup_cards` models + admin (M) — migration 0001 applied on dev; one-off checks 26/26 (model rules,
  approval, values, admin pages) + 4/4 (admin save path), all rolled back
  - `Attribute`, `CardType` (+ attribute schema), `Card` (`is_demo`, `external_key`, `extra`), `CardValue` (number | date + precision), `Tag`.
  - Admin: value inlines, filters (type/status/tag/popularity), bulk approve/reject; schema validation before approve.
  - Done when: a new type (e.g. "Futbolcu" with "transfer ücreti") is defined in admin only, no code change.
  - Built: `values.py` (pure: partial dates as year/month/day ints, negative year = MÖ, precision, Turkish number/date
    display), `CardTypeAttribute` (required/order) + `CardTypeField` (display fields → `Card.extra`), `Tag` tree.
    `services.py`: `approval_problems` (blocking, incl. Turkish title required) / `review_warnings` (popularity < 20,
    no source, demo),
    `set_status`. Admin: type's extra fields as inputs, value choices limited to the type, card type read-only after
    creation, approve/reject/staging actions, approval re-checked after inline save, review column ⛔/⚠.
- [x] **1.2** Demo seed `seed_lineup_demo` (S): 60 approved demo cards (İl: nüfus/yüzölçümü + Bölge; Olay: tarih;
  Film: tarih + Yönetmen) with FICTIONAL names and random values (seeded, idempotent), ties for 1999, `--purge`.
- [x] **1.3** Admin import (M/L) — check 19/19 (rolled back). Large files are synchronous for now (max 5000 rows);
  move to Celery when a real source needs it (Phase 7).
  - Per-type xlsx template generated from the schema → upload → dry-run preview with per-row errors → confirm →
    upsert by `(card_type, external_key)` into staging. `CardImport` record keeps the report; large files run in Celery.
- [x] **1.4** Engine core + tests (M) — `lineup_games/engine/` (values.py, decks.py, timeline.py), 33 tests OK
  (`python manage.py test lineup_games`). Wrong card = life lost + card discarded; deck = target + lives (13).
  - DTOs, comparison with precision + ties, seeded RNG, base generator (popularity threshold, min gap, category mix),
    `TimelineGenerator`, slot validation, lives (3), win (line reaches 10 cards).
  - Done when: tests pass; same seed + pool → same deck.
- [x] **1.5** `lineup_games` runs + API (M) — `/api/v1/lineup/games/runs/` (GET playing + recent, POST start),
  `runs/<id>/`, `runs/<id>/moves/` {slot}; end-to-end check 19/19 (rolled back).
  - `Run` (mode, seed, params, frozen deck ids, lives, score, `dealt_at`, status), `Move` log; start / state / move.
    Row lock against double submit. Done when: API E2E; no unrevealed value ever appears in a response.
- [x] **1.6a** Mobile Timeline: tap-a-gap placement, correct/wrong feedback (color + haptics), end screen (M) —
  checked on the Honor
- [x] **1.6b** Mobile Timeline: drag & drop with auto-scroll (M) — checked on the Honor
- [x] **1.9** Move timer removed (S, 2026-11-22, by request): engine/API/mobile countdown, `Move.timed_out` dropped
  (migration 0002), `LINEUP_MOVE_*` settings gone; engine tests 31 OK, API check 5/5 (rolled back).
  `elapsed_ms` capped at the column limit (a run can be resumed weeks later).
- [x] **1.7** "Hata bildir" on a card (S) — result banner button + long press on a line card; checked on the Honor
- [x] **1.8** `docs/FLOW_lineup.md` updated (card pool/import + timeline run diagrams).

## Phase 2: Streak mode + energy
- [x] **2.1** Engine streak + tests (S/M) — `engine/streak.py`: higher/lower, ties (also precision ties) accept both,
  1 life, `can_continue` / `resume` (max 1 per run; the API for it comes with the reward in 5.1). Revealed card always
  becomes the open card. `decks.streak_deck`: up to 60 cards, famous cards first, gap to the previous card shrinks
  (positions 1-5 easy gap, 6-15 normal, then none; farthest card when none fits). Statuses moved to `engine/status.py`
  (+ `abandoned`).
- [x] **2.2** Energy (S) — `engine/energy.py` (settle / spend / grant / next_at / full_at / in_grace), `Energy` model
  (stored + since, created full), settings `LINEUP_ENERGY_MAX` 5, `_REFILL_MINUTES` 25, `_GRACE_DAYS` 3 (date_joined).
  1 point per Timeline/Streak start, spent in the start transaction under a row lock. Engine tests 52 OK.
- [x] **2.3** API (S) — `GET home/` (energy with seconds to next/full, playing run per mode, best streak, timeline
  wins); `POST runs/ {mode: streak}`; `moves/ {guess}`; `runs/?mode=`; starting a mode abandons its playing run;
  409 `no_energy` / `invalid_guess`. `Run.score` stored (migration 0003 fills old timeline runs), `continues_used`,
  `Move.guess`; Energy admin. Check 26/26 (rolled back).
- [x] **2.4** Mobile (M) — `features/streak/` (open card with value, swipe up/down or buttons, history, end panel with
  record + disabled "Reklam izle, devam et"), `home/energy_widgets.dart` (live countdown, "Enerjin bitti" dialog with
  disabled ad/Pro buttons), home tiles with resume/record, ⚡1 on start buttons. Checked on the Honor.
- Phase 2 done 2026-11-22.
- [x] **2.5** FLOW updated (energy + streak run diagram).

## Phase 3: Daily puzzle + share
- [x] **3.1** Engine (S) — `engine/daily.py`: 6 cards, 3 attempts; per position 🟩 right (inside the card's rank
  range, so ties accept either place) / 🟨 one place off / 🟥 further; solved = all right; `solution`.
  `decks.daily_deck`: normal difficulty (popularity ≥ 40, 4 years / 12% gap), else the whole pool; never dealt
  already sorted. Engine tests 61 OK.
- [x] **3.2** API (S/M) — `DailyPuzzle` (unique date + number, Europe/Istanbul, random playable attribute, frozen
  deck, created by the first request of the day), `DailyPlay` (user + puzzle unique, attempts with marks, status).
  `GET daily/` (cards in the current order, values + solution + share text only when finished, seconds to the next
  puzzle), `POST daily/attempts/ {number, order}` (409 `daily_expired` / `daily_over` / `invalid_order`; free).
  Home gets `daily`. Admin: puzzles with plays. Migration 0004; check 24/24 (rolled back).
- [x] **3.3** Mobile (M) — `features/daily/`: reorderable list (handle = instant drag, card = long press), marks of
  the last attempt stay on unmoved cards, attempt rows, result with values + "Sonucu paylaş" (`share_plus`),
  countdown to the next puzzle (reloads when it starts), home tile status. Checked on the Honor (play + share).
- [x] **3.4** FLOW updated (daily puzzle + share diagram).
- [x] **3.5** Feedback (S, 2026-11-22): new puzzle every morning at 07:30 Istanbul (`LINEUP_DAILY_RESET`, before it
  the previous day's puzzle stays; boundary check 6/6, API check 24/24 rolled back). Card report on the puzzle via a
  🚩 button, only on the result list (long press is the drag while playing; by request no report while playing).
- Phase 3 done 2026-11-22.

## Phase 4: Account linking + profile
- [x] **4.1a** Shared `accounts` (S, [shared]): `POST auth/guest/claim/ {email, password, username?}` turns the
  signed-in guest into a regular account (same row = same progress; email unique per app, Django password
  validators, username not `guest-...`), old sessions revoked, new token pair. Non-guest → 409 `not_guest`, so
  Saving is unaffected. Login on a new device = existing `auth/login/`.
- [ ] **4.1b** Google sign-in (server verifies the ID token; Google id per app), link to guest — **deferred by request
  (2026-11-22)**; email + password comes first.
- [x] **4.2** Profile/stats (S) — `GET profile/`: Timeline played/wins/best, Streak played/best, daily played/solved/
  current + best solve streak/attempt distribution. `engine.daily.streaks` (consecutive puzzle numbers; today's open
  puzzle does not break it) + test (62 OK); home `daily.streak`. Check 22/22 with 4.1a (rolled back).
- [~] **4.3** Mobile (M) — session states `SessionNeedsLogin` (registered account without a session: logged out,
  frozen, expired → `/login`, never a silent new guest) and `SessionInactive` (`/inactive`: reopen or log out);
  `TokenStore.account` (login name; guest credentials dropped once registered). Screens: login (from the consent
  screen on a new device, from the profile for a guest with a warning, "Misafir olarak yeni başla"), profile
  (stats, legal texts, logout / freeze / delete with password; a guest confirms with its stored password), "Hesabını
  kaydet". Home: profile icon, 🔥 daily streak. Home/profile data follow the signed-in user. `flutter analyze` clean;
  waiting on the device check.
- [x] **4.4** FLOW updated (session: claim, login, inactive).

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
- [ ] **9.0** Server deploy (deferred from 0.7 by request; run when the user decides):

```powershell
# Production server (home server), after the push:
#  1) copy the Firebase key by hand (never via git), e.g. USB stick / scp:
#     dev PC  backend/secrets/firebase-lineup.json  ->  server  <repo>/backend/secrets/firebase-lineup.json
#  2) on the server, in the repo folder:
git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap          # registers lineup + publishes its legal texts
docker compose exec web python manage.py send_test_push lineup --title "Sunucudan"   # FCM key check (any device)
#  3) dev PC: VS Code F5 "Line Up (production, release)" (or: cd mobile_lineup; flutter run --release)
#     Expect: consent -> guest -> home, server line https://appmanager.com.tr/api/v1 "Sunucu: ok".
#     (Release builds hide the dev tools; the guest is a NEW account on the production DB.)
```

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
- ~~Timer: 10 s (+2 s grace) on Streak and Timeline~~ → 2026-11-22: no move timer in any mode (by request).
- Streak has no difficulty picker: difficulty rises with the streak (2.1). New-player grace = 3 days (tunable).
- Defaults to tune later: Timeline win = line reaches 10 cards (start card + 9), 3 lives; Streak 1 life + one ad
  continue per run; energy max 5, +1 every 25 min, no limit for new players' first days.
- Fake test data is fine until Phase 7, flagged `is_demo`.
- Daily puzzle: a new one at 07:30 Istanbul (by request); only the current puzzle is playable (archive = Pro, 5.3). Share text has no card names (no spoilers);
  the invite link joins it in Phase 6. Daily streak (consecutive days) comes with the profile stats (4.2).
- Accounts (Phase 4): no "forgot password" yet (needs outgoing email; plan with Google sign-in or before release).
  Logging in from a guest leaves that guest on the server (unused; could be cleaned up later).
