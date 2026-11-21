# Line Up (Flutter, Android)

Client of the shared app_manager backend (client slug `lineup`). Rules: repo root `CLAUDE.md`; tasks: `PROGRESS_lineup.md`.

```powershell
flutter pub get
flutter emulators --launch <id>        # dev loop on the emulator (backend at http://10.0.2.2)
flutter run                            # r = hot reload, R = hot restart, q = quit
# a phone (USB or wireless adb): forward the phone's port 8000 to the PC's nginx (port 80), once per connection
adb reverse tcp:8000 tcp:80
flutter run --dart-define=API_URL=http://localhost:8000/api/v1
flutter run --release                  # production backend (https://appmanager.com.tr)
flutter analyze
```

`lib/`: `config.dart` (API URL) · `router.dart` (go_router, follows the session) · `core/` (API client with JWT
renewal, secure token store, models, providers) · `features/<feature>/` (screens + controllers + services).
