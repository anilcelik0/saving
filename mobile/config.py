import os

import flet as ft

APP_SLUG = "saving"

# Android emulator reaches the host machine via 10.0.2.2; desktop runs talk to localhost.
ANDROID_DEFAULT_URL = "http://10.0.2.2/api/v1"
DESKTOP_DEFAULT_URL = "http://localhost/api/v1"

# A real phone needs the server's address baked into the build: copy local_config.example.py to local_config.py
# (git-ignored) and set API_URL, e.g. the computer's LAN IP "http://192.168.1.20/api/v1".
try:
    from local_config import API_URL as LOCAL_API_URL
except ImportError:
    LOCAL_API_URL = None


def api_base_url(platform) -> str:
    if url := os.getenv("SAVING_API_URL") or LOCAL_API_URL:
        return url.rstrip("/")
    if platform == ft.PagePlatform.ANDROID:
        return ANDROID_DEFAULT_URL
    return DESKTOP_DEFAULT_URL
