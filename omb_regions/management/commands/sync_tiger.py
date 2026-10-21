import json
import os
import tempfile
import zipfile
from typing import TYPE_CHECKING

import requests
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from omb_regions.models import WGS_SRID, County, State

if TYPE_CHECKING:
  from typing import Any, Literal


class Command(BaseCommand):
  help = "Downloads and imports US States and Counties from Census TIGER/Line"

  LEGACY_COUNTY_YEAR = 2014

  CURRENT_TIGER_URL: str = (
    "https://www2.census.gov/geo/tiger/GENZ{year}/shp/"
    "cb_{year}_us_{kind}_{resolution}.zip"
  )
  LEGACY_TIGER_URL: str = (
    "https://www2.census.gov/geo/tiger/GENZ{year}/cb_{year}_us_{kind}_{resolution}.zip"
  )

  def add_arguments(self, parser: Any) -> None:
    parser.add_argument(
      "--year",
      type=int,
      default=2023,
      help="Census TIGER/Line year to import.",
    )
    parser.add_argument(
      "--resolution",
      type=str,
      default="500k",
      choices=["500k", "20m", "5m"],
      help="Cartographic shape resolution to import.",
    )
    parser.add_argument(
      "--missing-only",
      action="store_true",
      help="Only create missing FIPS rows; do not update existing geometries.",
    )

  def handle(self, *args: Any, **options: Any) -> None:
    year: int = options["year"]
    resolution: str = options["resolution"]
    missing_only: bool = options["missing_only"]

    with tempfile.TemporaryDirectory() as tmp_dir:
      # Process States
      shp = self._download_and_extract(
        self._build_tiger_url("state", year, resolution),
        tmp_dir,
        "state",
        State,
      )
      self._import_states(shp, missing_only)

      # Process Counties
      shp = self._download_and_extract(
        self._build_tiger_url("county", year, resolution),
        tmp_dir,
        "county",
        County,
      )
      self._import_counties(shp, missing_only)
      self._import_legacy_counties(
        tmp_dir,
        resolution,
        missing_only,
      )

    self.stdout.write(self.style.SUCCESS("Import and geometry processing complete."))

  def _build_tiger_url(self, kind: str, year: int, resolution: str) -> str:
    if year <= 2013:
      tiger_url = self.LEGACY_TIGER_URL
    else:
      tiger_url = self.CURRENT_TIGER_URL
    return tiger_url.format(
      kind=kind,
      year=year,
      resolution=resolution,
    )

  def _download_and_extract(
    self,
    url: str,
    extract_to: str,
    kind: Literal["state", "county"],
    Model: type[State] | type[County],
    shp_name_contains: str | None = None,
  ) -> str:
    verbose_name_plural = Model._meta.verbose_name_plural
    self.stdout.write(f"Downloading {verbose_name_plural} from Census Bureau...")
    response = requests.get(url, stream=True, timeout=(10, 120))
    try:
      response.raise_for_status()
    except requests.HTTPError as error:
      raise CommandError(
        f"Could not download {verbose_name_plural} from {url}."
      ) from error

    zip_path = os.path.join(extract_to, f"{kind}.zip")
    with open(zip_path, "wb") as f:
      for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)

    self.stdout.write(f"Extracting {verbose_name_plural}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
      zip_ref.extractall(extract_to)

    # Find the .shp file in the extracted files
    for root, _, files in os.walk(extract_to):
      for file in files:
        file_name = file.lower()
        if file.endswith(".shp") and (
          f"_{kind}_" in file_name
          or (shp_name_contains is not None and shp_name_contains in file_name)
        ):
          return os.path.join(root, file)

    raise FileNotFoundError(f"Could not find .shp file for {verbose_name_plural}.")

  def _import_states(self, shp_path: str, missing_only: bool) -> None:
    self.stdout.write(self.style.SUCCESS("--- Importing States ---"))
    layer = DataSource(shp_path)[0]
    created = 0
    updated = 0
    skipped = 0

    with transaction.atomic():
      for feature in layer:
        fips2 = str(feature.get("STATEFP"))
        if missing_only and State.objects.filter(fips2=fips2).exists():
          skipped += 1
          continue

        state = State(
          fips2=fips2,
          code=f"{fips2}000",
          name=str(feature.get("NAME")),
          postal_code=str(feature.get("STUSPS")),
          shape=self._as_multipolygon(feature.geom.geos),
        )
        state.set_sq_miles()
        _, was_created = State.objects.update_or_create(
          fips2=state.fips2,
          defaults={
            "code": state.code,
            "name": state.name,
            "postal_code": state.postal_code,
            "shape": state.shape,
            "sq_miles": state.sq_miles,
          },
        )
        if was_created:
          created += 1
        else:
          updated += 1

    self.stdout.write(
      self.style.SUCCESS(
        f"Imported {created} states ({updated} updated, {skipped} skipped)."
      )
    )

  def _import_counties(
    self,
    shp_path: str,
    missing_only: bool,
    *,
    code_filter: set[str] | None = None,
  ) -> None:
    self.stdout.write(self.style.SUCCESS("--- Importing Counties ---"))
    layer = DataSource(shp_path)[0]
    states = State.objects.in_bulk(field_name="fips2")
    created = 0
    updated = 0
    skipped = 0

    with transaction.atomic():
      for feature in layer:
        county_code = str(feature.get("GEOID"))
        if code_filter is not None and county_code not in code_filter:
          continue
        if missing_only and County.objects.filter(code=county_code).exists():
          skipped += 1
          continue

        state = states.get(county_code[:2])
        if state is None:
          raise CommandError(f"State instance not found for county {county_code}.")

        county = County(
          code=county_code,
          fips2=county_code[:2],
          fips3=county_code[2:],
          name=f"{feature.get('NAME')}, {state.postal_code}",
          postal_code=state.postal_code,
          shape=self._as_multipolygon(feature.geom.geos),
          state=state,
        )
        county.set_sq_miles()
        _, was_created = County.objects.update_or_create(
          code=county.code,
          defaults={
            "fips2": county.fips2,
            "fips3": county.fips3,
            "name": county.name,
            "postal_code": county.postal_code,
            "shape": county.shape,
            "sq_miles": county.sq_miles,
            "state": county.state,
          },
        )
        if was_created:
          created += 1
        else:
          updated += 1

    self.stdout.write(
      self.style.SUCCESS(
        f"Imported {created} counties ({updated} updated, {skipped} skipped)."
      )
    )

  def _import_legacy_counties(
    self,
    tmp_dir: str,
    resolution: str,
    missing_only: bool,
  ) -> None:
    legacy_dir = os.path.join(tmp_dir, "legacy-counties")
    os.makedirs(legacy_dir, exist_ok=True)
    shp = self._download_and_extract(
      self._build_tiger_url("county", self.LEGACY_COUNTY_YEAR, resolution),
      legacy_dir,
      "county",
      County,
    )
    current_codes = set(County.objects.values_list("code", flat=True))
    missing_codes = {
      code for code in self._iter_county_codes(shp) if code not in current_codes
    }
    if not missing_codes:
      return
    self._import_counties(
      shp,
      missing_only=missing_only,
      code_filter=missing_codes,
    )

  def _iter_county_codes(self, shp_path: str) -> list[str]:
    layer = DataSource(shp_path)[0]
    return [str(feature.get("GEOID")) for feature in layer]

  def _as_multipolygon(self, geometry: GEOSGeometry) -> MultiPolygon:
    if geometry.srid is None:
      geometry.srid = WGS_SRID
    geometry = GEOSGeometry(self._strip_z_coordinates(geometry.geojson))
    geometry.srid = WGS_SRID
    if isinstance(geometry, MultiPolygon):
      return geometry
    if isinstance(geometry, Polygon):
      return MultiPolygon(geometry, srid=geometry.srid)
    raise CommandError(
      f"Expected Polygon or MultiPolygon geometry, got {geometry.geom_type}."
    )

  def _strip_z_coordinates(self, geojson: str) -> str:
    geometry = json.loads(geojson)

    def strip_coords(coords: object) -> object:
      if not isinstance(coords, list):
        return coords
      if coords and isinstance(coords[0], (int, float)):
        return coords[:2]
      return [strip_coords(coord) for coord in coords]

    geometry["coordinates"] = strip_coords(geometry["coordinates"])
    return json.dumps(geometry)
