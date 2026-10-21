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
- `sync_static_regions` loads the curated and federal static region definitions.

Upstream OMB bulletins and TIGER yearly releases are immutable, so running the
same bulletin and TIGER year in two projects yields identical data. Pin and
document the bulletin and year you ingest.

## Models

- `State`: US states keyed by FIPS.
- `County`: counties keyed by 5-digit FIPS, with a polygon `shape`.
- `Region`: aggregations above the county (OMB CBSA, MSA, MIC, MDIV, CSA, Census
  regions and divisions, and custom categories). Carries a `delineation_bulletin`
  and a `counties` membership relation.

## Delineation versioning

`Region.delineation_bulletin` records which OMB bulletin a region's boundaries
came from. Data keyed to a bulletin can join `Region` on it to reconstruct the
membership that was in effect at that time, instead of always seeing the latest
boundaries.

## License

MIT. See [LICENSE](LICENSE).
