# PROGRESS: Line Up (`lineup`)

Phase and task tracking for the Line Up client (data-driven card ordering game). Update whenever a task is done or the plan changes.
Rules live in `CLAUDE.md` (Core Design Rule 8). Original brief (input only): `docs/BRIEF_lineup.md`.
Legend: `[x]` done · `[~]` in progress / waiting on user · `[ ]` todo · Size: S / M / L (L = split before starting)

---

## ⏳ Waiting on user (pending commands)

```powershell
# Left from Phase 6 (user tests on 2026-11-23):
#  - Reminders: Profil > Bildirimler on. With LINEUP_ENERGY_GRACE_DAYS=0 + LINEUP_ENERGY_REFILL_MINUTES=2 in .env
#    (`docker compose up -d web`) spend energy, close the app -> "Enerjin doldu" ~10 min later (inexact);
#    "Günlük bulmaca hazır" at 07:30. Remove the .env lines afterwards.
#  - Invite link on the phone + its web page (http://localhost/lineup/c/KOD):
adb shell am start -a android.intent.action.VIEW -d "https://appmanager.com.tr/lineup/c/KOD" tr.com.appmanager.lineup

# Phase 7 (admin, dev PC): restart web (code changed; migrations already applied)
docker compose restart web
#  - Kart türleri: template links "Excel · JSON"; Kartlar içe aktar accepts .xlsx / .csv / .json -> preview with checks
#  - Kart türleri > "Dağılım raporu" (+ set "hedef kart sayısı")
#  - 7.5 / 7.6 real card sets (deletes the demo pool, puzzles and challenges, so yours to run; try --dry-run first):
docker compose exec web python manage.py load_lineup_sets --reset --dry-run
docker compose exec web python manage.py load_lineup_sets --reset
#    rebuild a set from its sources (TÜİK each February, goals as they change):
docker compose exec web python lineup_cards/datasets/build_sets.py provinces
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
- [x] **4.3** Mobile (M) — session states `SessionNeedsLogin` (registered account without a session: logged out,
  frozen, expired → `/login`, never a silent new guest) and `SessionInactive` (`/inactive`: reopen or log out);
  `TokenStore.account` (login name; guest credentials dropped once registered). Screens: login (from the consent
  screen on a new device, from the profile for a guest with a warning, "Misafir olarak yeni başla"), profile
  (stats, legal texts, logout / freeze / delete with password; a guest confirms with its stored password), "Hesabını
  kaydet". Home: profile icon, 🔥 daily streak. Home/profile data follow the signed-in user. Checked on the Honor.
- Phase 4 done 2026-11-22 (Google sign-in deferred).
- [x] **4.4** FLOW updated (session: claim, login, inactive).

## Phase 5: Monetization
Built and checked with simulations (by request 2026-11-22); the store / ad accounts and the real end-to-end checks
are at the end (Phase 9: 9.1-9.3), because SSV callbacks and RevenueCat webhooks need the public server.
- [x] **5.0** Package name final: `tr.com.appmanager.lineup` (2026-11-22). Play Console app, AdMob app + rewarded unit
  (SSV callback URL), RevenueCat project → moved to 9.1 (by request).
- [x] **5.1** Shared `billing` (M, [shared]): `RewardIntent` (ask → ad custom_data → SSV grants once, unique
  transaction id, 30 min TTL, re-checked at grant), `admob.verify` (ECDSA P-256 over the query before `&signature=`,
  Google keys cached 24 h, refetched on an unknown key id), registry `register_reward(kind, check, grant)` +
  `set_daily_cap(app, n)` (like `support.registry`; Saving registers nothing). Endpoints `billing/rewards/`,
  `rewards/<id>/`, `admob/ssv/` (public, 200 on any valid signature, 403 otherwise), DEBUG-only `dev/rewards/<id>/
  grant/`. Lineup (`lineup_games/rewards.py`): `lineup.energy` (+1, refused when full / unlimited),
  `lineup.continue` (one continue per run, both modes), cap `LINEUP_DAILY_AD_CAP` 10/day.
  Engine: Timeline continue (`can_continue` / `resume`, 1 life, deck 13 → 14 so the continue never runs dry) + tests
  (65 OK). Account deletion also removes the user's store events.
- [x] **5.2** Mobile rewarded flows (M): `features/billing/reward_ads.dart` (intent → UMP consent → test ad with
  SSV options → dev grant in debug / poll the intent in release), "Enerjin bitti" ad button with ads left today,
  `ContinueOffer` on the Timeline + Streak end panels.
- [x] **5.3** Pro (M): `Entitlement` (key `pro`, expiry, source revenuecat/admin/dev; admin can give Pro to
  testers), RevenueCat webhook `billing/revenuecat/<app>/` (Authorization = `BILLING_REVENUECAT_WEBHOOK_SECRETS`,
  idempotent by event id, late events ignored, CANCELLATION keeps it until expiry, EXPIRATION ends it, TRANSFER
  ends the old user's). Lineup: Pro = unlimited energy, `POST runs/<id>/continue/` without an ad, daily archive
  (`daily/archive/`, `daily/?number=`, archive plays are `late` → no streak). DEBUG-only `dev/entitlements/`.
  Backend check 41/41 (signed SSV with a test key, RevenueCat events; rolled back, cache restored).
- [x] **5.4** Mobile Pro (M): Pro screen (status, benefits, debug-only Pro toggle), home Pro tile, archive screen,
  energy "sınırsız · Pro", Pro continue. Store purchase (`purchases_flutter`, restore) → 9.2 (needs the RevenueCat
  project + Play products). Checked on the Honor (after the fix: `set_entitlement` in its own transaction).
- Phase 5 done 2026-11-22 (store / ad accounts and real end-to-end checks in 9.1-9.3).
- [x] **5.5** UMP consent before the first ad + "Reklam gizlilik ayarları" in the profile where required; privacy +
  KVKK drafts updated for AdMob, Google Play, RevenueCat (abroad transfer). **Publishing them is a new version
  everyone re-accepts: run at release (9.3), or on dev to try the re-consent flow.** Have the texts reviewed by a
  lawyer before release (KVKK art. 9 abroad transfer).
- [x] **5.6** FLOW updated (rewarded ad + Pro diagram).

## Phase 6: Invite challenges + push
Decisions (2026-11-22): a challenge is made from a finished run (same deck, its score is the target); shared by
link / code and optionally sent to a username (push). Both modes; same rules for both sides (continue included).
- [x] **6.1** `lineup_social` (M): `Challenge` (6-char code without 0/O/1/I, one per source run, 7 days
  `LINEUP_CHALLENGE_DAYS`), `ChallengeInvite` (to a username → push + incoming list), `ChallengeEntry` (free challenge
  run on the same frozen deck, one per user, accept again = same run). `Run.is_challenge`: not resumed from home,
  not abandoned by normal starts, no records / stats. `lineup_games.signals.run_finished` → push the creator once.
  API `lineup/social/challenges/` (lists, create), `<code>/`, `accept/`, `send/`.
- [x] **6.2** Links (M): public page `/lineup/c/<code>` (who challenged, code, how to join; 404 page for unknown) and
  `/.well-known/assetlinks.json` served by Django for every client with `android_package` + `ANDROID_SHA256_<APP>`
  fingerprints (instead of an nginx file: config, not a file per server). Release fingerprint → 9.4.
- [x] **6.3** Shared `notifications` (M, [shared]): `DeviceToken` (token follows the last user who registered it),
  `POST/DELETE notifications/devices/`, `notify(user, title, body, data)` → Celery `send_push` after commit (only
  active accounts; dead tokens deleted). Check 28/28 (rolled back; pushes captured).
- [x] **6.4** Mobile (L): game screens open a given run (`?run=&challenge=`, providers per run id), end panel
  "Arkadaşına meydan oku" / "Sonucu gör", challenges list (incoming / played / sent, join by code), challenge screen
  (share, send to username, accept, results), home tile with new count; App Link intent filter + router keeps a link
  until sign-in; push: token registered for the signed-in user (moved on account change, removed on logout / freeze /
  delete), tap opens the challenge, SnackBar while open; local reminders (`flutter_local_notifications`, inexact):
  energy full, daily puzzle 07:30, switches in the profile. compileSdk 37 (plugin requirement), desugaring on.
  Challenges + pushes checked on two devices; local reminders and the invite link are tested 2026-11-23 (see top).
- [x] **6.5** FLOW updated (challenge + push diagram).
- Phase 6 done 2026-11-22 (reminder / link device check pending, by the user).

## Phase 7: Real data pipeline (deliberately last)
Decision 2026-11-22 (by request): **no live source connection.** The Wikidata adapter (sources, presets, page views,
monthly refresh) was built and then removed (migration 0004, its tables were empty); card data comes later as JSON
files through the same import pipeline. Kept: the automatic checks and the report.
- [x] **7.1** JSON import (S): `.json` upload (a list of cards or `{"cards": [...]}`; keys = template columns; numbers
  as JSON numbers or text, dates "1453" / "1453-05-29" / "-490", tags a list or comma text) next to Excel / CSV;
  per type JSON template (`{"card_type", "columns": {key: explanation}, "cards": [example]}`), "Şablon: Excel · JSON".
- [x] **7.2** Checks (M) in `importer.validate` (every format, warnings only): outliers (robust z > 5, log scale for
  positive numbers), duplicate titles (in the file or another external key), low popularity, future dates, no Turkish
  title, missing values. Popularity is given in the file (0-100).
- [-] **7.3** Monthly refresh: dropped with the live source.
- [x] **7.4** Report (S): `CardType.target_count`, "hedef" column, admin "Dağılım raporu" (approved vs target,
  staging / rejected / demo / non-Turkish counts, popularity buckets, value range per attribute).
  Check 15/15 (JSON parse / template / admin upload / apply / checks / report; rolled back).
- [~] **7.5** Purge demo cards: done by `load_lineup_sets --reset` (7.6), waiting for the user to run it on the dev DB.
  The production DB was never seeded (report: demo 0).
- [~] **7.6** First real card sets (2026-11-24, by request), `backend/lineup_cards/datasets/`:
  `build_sets.py` (dev tool, run by hand; the app never connects to the sources) writes one JSON per set in the
  import format + the card type definition; `manage.py load_lineup_sets [sets] [--reset] [--dry-run]` ensures the
  types / attributes / fields, runs the import pipeline (validate, apply, CardImport record), sets per-value sources
  and approves. `--reset` deletes every card, card import, daily puzzle (+ plays) and challenge, and abandons runs
  being played (frozen decks would answer `card_missing`).
  - İl (81): population 31.12.2025 from TÜİK ADNKS (nip.tuik.gov.tr; the 81 add up to TÜİK's 86 092 168), area
    from Harita Genel Müdürlüğü's 2026 province areas (TÜİK publishes density only). Popularity from population.
  - Futbolcu (35): Süper Lig players with 100+ league goals (English Wikipedia list, table updated 9 May 2026, cites
    Mackolik; revision pinned), clubs with goals as a display field, club tags (a Galatasaray-only set is a tag
    filter). Active players' goals change: rebuild.
  - Film (25): IMDb rating (official dataset title.ratings) + year (Wikidata earliest publication date) on the shared
    `date` attribute, director, Turkish title from Turkish Wikipedia. **IMDb data is licensed for personal /
    non-commercial use only: license it or drop the rating before release (9.x).**
  Check (rolled back): reset + load 141 cards all approved, no warnings; timeline easy/normal/hard and streak start on
  all 5 attributes, daily puzzle builds: 21/21.

## Phase 8: Visual design (dedicated phase)
Design canvas (claude.ai artifact, private): 3 directions per game. Choices (2026-11-23): daily puzzle = "Gece" layout
(attempt grid + value axis) on the light theme; Zaman Çizgisi, Seri and home = "Gündüz". Game by game, user tests each.
- [x] **8.0** Shared light theme `core/theme.dart` (palette `LU`, Space Grotesk headings/numbers + Inter via
  `google_fonts`, buttons / cards / app bar, `CircleIconButton`). Fonts are fetched at runtime and cached; bundle
  them as assets before release (9.x).
- [x] **8.1** Daily puzzle screen: header (#n · attribute, daily streak, archive), attempt grid (marks with icons, current
  row outlined), vertical value axis, cards lifted while dragging, "Kontrol et"; result card (grid, share, countdown)
  + solution list with values and report flag. Approved by the user (2026-11-23).
  Attempts raised 3 -> 5 by request (`engine.daily.ATTEMPTS`; home payload sends `max_attempts`, profile distribution
  follows the server keys). Old plays keep their stored status.
- [x] Fix (shared `core`): `/api/v1/health/` answered 500 since 9490a6e (its DRF decorators had moved onto the new
  `assetlinks` view), so the dev home screen showed "Sunucu: hata". Decorators restored; health 200, assetlinks 200.
- [~] **8.2** Zaman Çizgisi (user's spec, 2026-11-23/24): the line fills the screen, **highest value on top** (display
  only: the client sends `slot = len(line) - screen gap`); the new card waits at the bottom as a dark row with "?".
  Drag without a magnet (2026-11-24, by request): the card stays under the finger while the cards part smoothly
  where it would go (gap judged against the resting line, so it never flickers); letting go glides it into the gap
  (or back home) and places it (n cards = n + 1 gaps); the next card slides in at the bottom. The line rests centred
  in room for one more row, so a right card turns over exactly where it was dropped. The start card is dragged onto
  the empty line first (display only, the server already placed it). The whole line fits without scrolling (rows,
  then spacing, shrink). Placed card green until the next move; a wrong card simply disappears (no ghost, no banner),
  the lost heart pops. Committed 06484ba (before the smooth drag); smooth drag waiting for the user's test.
- [x] **8.3** Seri: Gündüz layout kept (open card, up / down buttons around the swipe card); the previous-cards list is
  replaced by a value axis on the left: every revealed card spread evenly (highest on top), the open card's dot blue;
  no scrolling / re-centring (by request); value only when crowded. Revealed card green / red instead of a banner.
  Right column top-aligned, open and hidden cards with a fixed minimum height (nothing jumps between cards).
  Backend: `engine.values.sort_key` + `sort` in revealed card payloads (display order only), engine test added (66 OK).
  Committed 06484ba.
- [~] **8.4** Home (Gündüz, first screen): LineUp logo + profile button, energy box (a bolt per point), today's puzzle
  as the big blue card (number, streak, "Bugünün 6 kartını sırala" / continue / solved / lost, card shapes),
  Zaman Çizgisi and Seri side by side (record or the run being played, cost), challenges row with a red "n yeni"
  badge, outlined Pro row; guest note under the energy box. Server line kept as a small footer until release (9.0
  deploy check), dev tools link debug only. Backend: `cards` in the home daily payload. Waiting for the user's test.
- [ ] **8.5** The remaining screens (profile, Pro, challenges, login, archive) in the same theme.
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

- [ ] **9.1** (user) Play Console app `tr.com.appmanager.lineup`, AdMob app (replace Google's TEST app id in
  AndroidManifest) + rewarded unit with SSV callback `https://appmanager.com.tr/api/v1/billing/admob/ssv/`
  (AdMob "Verify URL" → 200), RevenueCat project + Play service credentials, entitlement `pro`, monthly / yearly
  products, webhook `https://appmanager.com.tr/api/v1/billing/revenuecat/lineup/` with an Authorization value =
  server `.env` `BILLING_REVENUECAT_WEBHOOK_SECRETS=lineup=<value>`.
- [ ] **9.2** Mobile purchases: `purchases_flutter` (appUserID = our user id), offerings on the Pro screen, restore;
  release build with `--dart-define=ADMOB_REWARDED_UNIT=...` (+ the RevenueCat public key). Real SSV + webhook test
  on an internal-test build.
- [ ] **9.3** `publish_legal_documents lineup` on the server (ads / subscription texts, 5.5).
- [ ] **9.4** App Links: Play Console > App signing SHA-256 → server `.env` `ANDROID_SHA256_LINEUP=...`; check
  `https://appmanager.com.tr/.well-known/assetlinks.json` and that an invite link opens the release app directly.
  Play Store link on the invite page.
- Icon/splash, signed AAB, Play forms (audience 13+, data safety: ads + advertising id + purchases), internal →
  closed test, metrics (D1/D7/D30, puzzle share rate, challenge accept rate).

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
- Monetization (Phase 5): rewards are granted only by the server (SSV, or the DEBUG-only dev grant on a dev PC);
  `BILLING_DEV_TOOLS` is forced off when DEBUG is off. Daily ad cap 10 (tunable). Archive plays never count for the
  daily streak.
- Challenges (Phase 6): the public invite page shows the creator's username and score (meant for sharing). Logging in
  from a guest on a phone moves that phone's push token to the new account.
