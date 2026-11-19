# Changelog

## Unreleased

- Initial extraction of the geography engine into a standalone GeoDjango app.
- `State`, `County`, and `Region` models with OMB delineation versioning.
- Ingest commands: `sync_tiger`, `sync_omb_regions`, `sync_static_regions`.
- Extensible `Region.category`: the library ships only base/federal categories;
  downstream projects add their own via `register_categories()`.
- `sync_static_regions` loads its `REGIONS` definitions from a configurable
  module (`--defs` argument or `OMB_REGIONS_STATIC_DEFS` setting), and builds a
  region only when every component resolves (partial definitions abort the run).
- PostGIS-backed integration test suite and a CI PostGIS service.
