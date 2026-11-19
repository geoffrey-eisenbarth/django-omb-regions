# django-omb-regions

Versioned US states, counties, and OMB regions for GeoDjango.

This is a reusable GeoDjango app that models US geography as time-versioned
`State`, `County`, and `Region` records, ingested from public upstream sources
(Census TIGER/Line and OMB delineation bulletins). OMB redraws metropolitan area
boundaries periodically, so each `Region` carries a `delineation_bulletin`, and
queries can resolve membership as of a given bulletin.

`omb_regions` is the current import name. The distribution name may change before
a public release, since OMB regions are only the metropolitan slice of what the
app models (it also ingests TIGER states and counties and supports custom region
taxonomies).

## Requirements

- Python >= 3.14
- Django >= 6.0
- PostGIS. The models use `MultiPolygonField`, so the database must be PostgreSQL
  with the PostGIS extension, and the host needs GDAL and GEOS installed.

## Installation

```bash
pip install django-omb-regions
pip install "django-omb-regions[ingest]"
```

The `ingest` extra adds `requests`, `pandas`, `titlecase`, `openpyxl`, and
`xlrd`, which are only needed when running the `sync_*` management commands, not
at serving time.

Add the app to your settings:

```python
INSTALLED_APPS = [
  # ...
  "django.contrib.gis",
  "omb_regions",
]
```

Then migrate:

```bash
python manage.py migrate omb_regions
```

## Populating the database

Each project populates its own database from upstream; there is no cross-project
sync. Run the ingest commands in order:

```bash
python manage.py sync_tiger
python manage.py sync_omb_regions
python manage.py sync_static_regions
```

- `sync_tiger` loads states and counties from Census TIGER/Line.
- `sync_omb_regions` loads OMB CBSA, MSA, MIC, MDIV, and CSA regions plus Census
  divisions and regions.
- `sync_static_regions` loads curated static region definitions.

### Custom static region definitions

`sync_static_regions` aggregates component county (or sub-region) codes into
`Region` rows from a declarative `REGIONS` list. By default it loads the bundled
federal definitions (`omb_regions.defs`). Point it at your own definitions
without editing the package via either the `--defs` argument or the
`DJANGO_OMB_REGIONS_STATIC_DEFS` setting (the argument wins):

```bash
python manage.py sync_static_regions --defs myproject.regions.defs
```

```python
# settings.py
DJANGO_OMB_REGIONS_STATIC_DEFS = "myproject.regions.defs"
```

The target module must expose a `REGIONS` list of mappings shaped like:

```python
REGIONS = [
  {
    "code": "900",
    "name": "Example Metro",
    "postal_code": "TX",
    "category": "MSA",
    "components": [("48001", "Anderson"), ("48003", "Andrews")],
  },
]
```

Each `components` entry is a `(code, label)` pair; `code` may be a county FIPS, a
whole-state FIPS (`NN000`), or another static region's code (resolved after it is
built). A definition is created only when every component resolves, so a typo or
a missing county aborts the run rather than silently building a partial region.

Upstream OMB bulletins and TIGER yearly releases are immutable, so running the
same bulletin and TIGER year in two projects yields identical data. Pin and
document the bulletin and year you ingest.

## Models

- `State`: US states keyed by FIPS.
- `County`: counties keyed by 5-digit FIPS, with a polygon `shape`.
- `Region`: aggregations above the county (OMB CBSA, MSA, MIC, MDIV, CSA, Census
  regions and divisions, and custom categories). Carries a `delineation_bulletin`
  and a `counties` membership relation.

## Custom categories

`Region.category` ships only the base and federal-standard categories
(`RegionCategory`: STATE, COUNTY, USCBR, USCBD, CSA, MSA, MDIV, MIC). Projects
that model their own region taxonomies (state planning regions, utility service
areas, bespoke study regions, and so on) register their categories at startup.

Define your categories as a `TextChoices` and register them from your app's
`AppConfig.ready()`:

```python
# myproject/regions/enums.py
from django.db.models import TextChoices


class MyCategory(TextChoices):
  COG = "COG", "Council of Governments Region"
  UTILITY = "UTILITY", "Utility Service Area"
```

```python
# myproject/regions/apps.py
from django.apps import AppConfig


class RegionsConfig(AppConfig):
  name = "myproject.regions"

  def ready(self):
    from omb_regions.enums import register_categories

    from .enums import MyCategory

    register_categories(MyCategory)
```

`register_categories` merges your members into the choices returned by
`region_category_choices()`, which `Region.category` uses. Because the field
stores that function by reference, registering categories does not create
migrations. `category` is a plain `CharField`, so choices affect validation and
admin display only, never the database schema; your category codes become valid
`Region.category` values once registered. You keep your own typed enum, so you
reference `MyCategory.UTILITY` in your code while the library stays generic.

## Delineation versioning

`Region.delineation_bulletin` records which OMB bulletin a region's boundaries
came from. Data keyed to a bulletin can join `Region` on it to reconstruct the
membership that was in effect at that time, instead of always seeing the latest
boundaries.

## Running the tests

The test suite is integration-first and exercises the models, managers,
resolvers, and `sync_static_regions` against a real PostGIS database, so it needs
PostgreSQL with PostGIS reachable. The database connection is read from
environment variables (defaulting to `postgres`/`postgres` on `localhost:5432`,
which matches the CI service):

Copy `.env.example` to `.env` and set the values there; `tests/settings.py` loads
it automatically via `python-dotenv`:

```bash
cp .env.example .env
uv run pytest
```

The test runner creates (and drops) its own `test_*` database, so the configured
role needs `CREATEDB`, and PostGIS must be installable on the test database
(either the role is a superuser or `template1` already has the extension).

## License

MIT. See [LICENSE](LICENSE).
