# TODO

Open work before (and around) a public release. Items 1 and 2 are the real
"is this publishable as a generic engine" blockers; the rest are cleanup.

## 1. Extensible region categories

`Region.category` is still a CLOSED `TextChoices` (`omb_regions/enums.py`,
`Geography`) with downstream, company-specific values baked in: `FROST`
(Frost Bank), `TPG` (Perryman Group), `EDR`, `EPR`, `COG`, `WDA`, `TOURISM`,
`BASIN`, and the various Texas district types. A generic, publishable engine
should ship only the base and federal-standard categories (STATE, COUNTY,
USCBR/USCBD Census regions and divisions, CSA/MSA/MDIV/MIC, etc.) and let a
downstream project register its own categories.

Approach: `category` is just a `CharField`; choices are only validation and
display. Ship base/federal choices in the library, then let downstream add
categories via a setting (e.g. `OMB_REGIONS_EXTRA_CATEGORIES`) or a
`register_category(code, label)` call, merged into the choices at runtime. The
curated company categories (FROST/TPG/Texas) then live in the private
downstream, which registers them before use.

## 2. Scrub `FROST` from library logic

A Frost Bank region code is hardcoded into general-purpose library code and must
be removed before publishing:

- `omb_regions/resolvers.py:31`
- `omb_regions/models.py:214` (`Region.is_metro`)
- `omb_regions/annotations.py` (four sites: lines ~98, ~136, ~167, ~221)

These bake a downstream category into resolution/annotation logic. Once item 1
lands, replace the hardcoded `FROST` handling with the configurable
metro-category mechanism (or drop it from the library entirely and move it
downstream).

## 3. Generic `sync_static_regions` loader

`omb_regions/management/commands/sync_static_regions.py` hardwires
`from omb_regions import defs`, so it can only load the package's own bundled
definitions. Make the loader generic: point it at a `REGIONS` module via a
setting or a `--defs <dotted.path>` argument, so a downstream project can load
its own curated region definitions without editing the package.

## 4. Move curated region defs to the private downstream

`omb_regions/defs/` should ship only federal-standard definitions
(`defs/census.py`). The curated company data (`defs/texas_*.py`, `defs/custom.py`,
curated `basins.py`, and any TPG/Texas `REGIONS`) belongs in the private
downstream project (or a small private `*-tpg` add-on), loaded via the generic
loader from item 3. Audit `defs/` and remove anything company-specific before
publishing.

## 5. Database-touching tests

The current `tests/` are DB-less smoke tests only; no test actually exercises the
models, managers, querysets, resolvers, or ingest commands against a database.
Add PostGIS-backed tests (the models use `MultiPolygonField`, so tests need a
PostGIS database and GDAL/GEOS on the host) covering at least: model creation and
constraints, the `current`/`versions`/`metros` managers, `resolve_region_code`,
and delineation-bulletin membership resolution. Wire a PostGIS service into CI so
these run.
