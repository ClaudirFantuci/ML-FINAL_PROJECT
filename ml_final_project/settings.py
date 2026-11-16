"""Configuracao minima do Django para servir o estimador de precos."""
import os
import secrets
from django.core.exceptions import ImproperlyConfigured
from pathlib import Path

import config as app_config  # config.py na raiz do projeto (coleta + modelo)

BASE_DIR = Path(__file__).resolve().parent.parent

PRODUCTION = os.environ.get("DJANGO_ENV") == "production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if PRODUCTION and not SECRET_KEY:
    raise ImproperlyConfigured("Configure DJANGO_SECRET_KEY em produção.")
SECRET_KEY = SECRET_KEY or secrets.token_urlsafe(64)
DEBUG = not PRODUCTION and os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]
if PRODUCTION and (not os.environ.get("DJANGO_ALLOWED_HOSTS") or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Configure hosts explícitos em DJANGO_ALLOWED_HOSTS.")
CSRF_COOKIE_SECURE = PRODUCTION
SECURE_SSL_REDIRECT = PRODUCTION
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "predictor",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ml_final_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "ml_final_project.wsgi.application"

DATABASES = {}  # este projeto não usa banco de dados

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Constantes do estimador (reaproveitadas do config.py da coleta)
CITY_NAME = app_config.CITY_NAME
CITY_CENTER = app_config.CITY_CENTER
