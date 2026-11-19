import os

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = "test-only-not-secret"

INSTALLED_APPS = [
  "django.contrib.contenttypes",
  "django.contrib.auth",
  "django.contrib.gis",
  "django_omb_regions",
]

DATABASES = {
  "default": {
    "ENGINE": "django.contrib.gis.db.backends.postgis",
    "NAME": os.environ.get("OMB_TEST_DB_NAME", "django_omb_regions_test"),
    "USER": os.environ.get("OMB_TEST_DB_USER", "postgres"),
    "PASSWORD": os.environ.get("OMB_TEST_DB_PASSWORD", "postgres"),
    "HOST": os.environ.get("OMB_TEST_DB_HOST", "localhost"),
    "PORT": os.environ.get("OMB_TEST_DB_PORT", "5432"),
  },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
