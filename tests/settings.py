SECRET_KEY = "test-only-not-secret"

INSTALLED_APPS = [
  "django.contrib.contenttypes",
  "django.contrib.auth",
  "django.contrib.gis",
  "omb_regions",
]

DATABASES = {
  "default": {
    "ENGINE": "django.contrib.gis.db.backends.postgis",
    "NAME": "omb_regions_test",
    "USER": "postgres",
    "PASSWORD": "postgres",
    "HOST": "localhost",
    "PORT": "5432",
  },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
