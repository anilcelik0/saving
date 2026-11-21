from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

# --- Core ---
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Behind nginx (+ Cloudflare Tunnel in production: HTTPS ends at Cloudflare, nginx forwards its scheme)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
# Production only (local runs are plain HTTP): cookies over HTTPS only (admin login), optional HSTS.
# HTTP -> HTTPS redirect is left to Cloudflare ("Always Use HTTPS").
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=False)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=0)

# Legal texts (privacy policy, KVKK notice): data controller shown in the published documents
LEGAL_CONTROLLER_NAME = env("LEGAL_CONTROLLER_NAME", default="")
LEGAL_CONTACT_EMAIL = env("LEGAL_CONTACT_EMAIL", default="")
# Account deletion: locked at request, permanently deleted after this many days (cancel by logging in)
ACCOUNT_DELETION_GRACE_DAYS = 30

# --- Apps ---
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
]
SHARED_APPS = [
    "accounts",
    "support",
    "notifications",
]
SAVING_APPS = [
    "saving_budget",
    "saving_invest",
    "saving_reports",
]
LINEUP_APPS = [
    "lineup_cards",
    "lineup_games",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + SHARED_APPS + SAVING_APPS + LINEUP_APPS

# Client applications served by this backend (slug -> config); `manage.py bootstrap` registers them (name,
# allow_guests) and publishes their legal texts (legal_texts/<slug>/).
CLIENT_APPS = {
    "saving": {"name": "Saving"},
    "lineup": {"name": "Line Up", "allow_guests": True},
}

# Line Up energy (Timeline / Streak starts cost 1): max points, minutes per point, no limit for new players' first days
LINEUP_ENERGY_MAX = env.int("LINEUP_ENERGY_MAX", default=5)
LINEUP_ENERGY_REFILL_MINUTES = env.int("LINEUP_ENERGY_REFILL_MINUTES", default=25)
LINEUP_ENERGY_GRACE_DAYS = env.int("LINEUP_ENERGY_GRACE_DAYS", default=3)

# Firebase service account keys, one per client app: <dir>/firebase-<slug>.json (git-ignored, copied by hand)
FIREBASE_CREDENTIALS_DIR = env("FIREBASE_CREDENTIALS_DIR", default=str(BASE_DIR / "secrets"))

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.AppScopedBackend"]
# USERNAME_FIELD is unique per app (not globally); handled by AppScopedBackend.
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache / Redis ---
REDIS_URL = env("REDIS_URL", default="redis://redis:6379")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/2",
    }
}

# --- Celery ---
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/1"
CELERY_TIMEZONE = "Europe/Istanbul"
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "accounts-flush-expired-tokens": {
        "task": "accounts.tasks.flush_expired_tokens",
        "schedule": crontab(hour=4, minute=0),
    },
    "saving-budget-daily-maintenance": {
        "task": "saving_budget.tasks.daily_budget_maintenance",
        "schedule": crontab(hour=0, minute=30),
    },
    # TCMB publishes rates around 15:30 on business days
    "saving-invest-daily-prices": {
        "task": "saving_invest.tasks.fetch_daily_prices",
        "schedule": crontab(hour=17, minute=0),
    },
    "accounts-delete-scheduled-accounts": {
        "task": "accounts.tasks.delete_scheduled_accounts",
        "schedule": crontab(hour=2, minute=15),
    },
    "support-purge-issue-attachments": {
        "task": "support.tasks.purge_issue_attachments",
        "schedule": crontab(hour=3, minute=30),
    },
}

# --- Market data (saving_invest) ---
TCMB_RATES_URL = env("TCMB_RATES_URL", default="https://www.tcmb.gov.tr/kurlar/today.xml")
ALTINKAYNAK_GOLD_URL = env("ALTINKAYNAK_GOLD_URL", default="https://static.altinkaynak.com/public/Gold")
# Withholding tax (stopaj, %) deducted from deposit interest when the maturity amount is computed
DEPOSIT_WITHHOLDING_RATE = Decimal(env("DEPOSIT_WITHHOLDING_RATE", default="17.5"))

# --- Auth ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- DRF / JWT ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.AppJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min", "guest": "10/hour", "support": "30/hour"},
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "NUM_PROXIES": 1,  # nginx -> real client IP for throttling
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    # Sliding session: each refresh issues a new refresh token, so active users never re-login.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=90)),
    "TOKEN_REFRESH_SERIALIZER": "accounts.serializers.AppTokenRefreshSerializer",
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --- I18N ---
LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

# --- Static / Media (served by nginx) ---
STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default="/vol/static")
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default="/vol/media")
# Private files (e.g. bank statements): never served by nginx, only read by Django/Celery.
PRIVATE_MEDIA_ROOT = env("PRIVATE_MEDIA_ROOT", default="/vol/private")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": PRIVATE_MEDIA_ROOT, "base_url": None},
    },
}
STATEMENT_MAX_UPLOAD_MB = 10
# Issue reports ("Sorun bildir"): attachment limits; files are deleted when the report is resolved/closed
# or after the retention period (support.tasks.purge_issue_attachments). nginx body limit: 20 MB.
ISSUE_ATTACHMENT_MAX_FILES = 3
ISSUE_ATTACHMENT_MAX_MB = 10
ISSUE_ATTACHMENT_RETENTION_DAYS = 30

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
