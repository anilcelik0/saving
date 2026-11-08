import os

import flet as ft

APP_SLUG = "saving"

# Android emulator reaches the host machine via 10.0.2.2. For a real device set SAVING_API_URL
# (or change this default) to the computer's LAN IP, e.g. http://192.168.1.20:8080/api/v1
ANDROID_DEFAULT_URL = "http://10.0.2.2:8080/api/v1"
DESKTOP_DEFAULT_URL = "http://localhost:8080/api/v1"


def api_base_url(platform) -> str:
    if url := os.getenv("SAVING_API_URL"):
        return url.rstrip("/")
    if platform == ft.PagePlatform.ANDROID:
        return ANDROID_DEFAULT_URL
    return DESKTOP_DEFAULT_URL
