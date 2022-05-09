from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "fake"
DEBUG = True

INSTALLED_APPS = (
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "graphene_django",
    "graphene_django_permissions",
    "tests",
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}

GRAPHENE = {
    "SCHEMA": "schema.schema",
    "MIDDLEWARE": [
        "graphene_django_permissions.middleware.GrapheneAuthorizationMiddleware",
    ],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "tests.urls"
WSGI_APPLICATION = "tests.wsgi.application"
