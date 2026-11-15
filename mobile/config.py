import os

APP_SLUG = "saving"

# Built app (flet build apk/aab): Flet sets FLET_PLATFORM inside the package -> production server over HTTPS.
PRODUCTION_URL = "https://appmanager.com.tr/api/v1"
# Development (`flet run`, also `flet run --android` with the Flet app on the phone: Python runs on this
# computer) -> the local Docker server. local_config.py (git-ignored, never packaged) may point elsewhere.
LOCAL_URL = "http://localhost/api/v1"

try:
    from local_config import API_URL as LOCAL_API_URL
except ImportError:
    LOCAL_API_URL = None


def is_packaged() -> bool:
    return os.getenv("FLET_PLATFORM") is not None


def api_base_url(platform=None) -> str:
    """SAVING_API_URL env var overrides everything (e.g. testing a dev run against production)."""
    if url := os.getenv("SAVING_API_URL"):
        return url.rstrip("/")
    if is_packaged():
        return PRODUCTION_URL
    return (LOCAL_API_URL or LOCAL_URL).rstrip("/")
