"""Small GEOS/ORM helpers for building real geographies in tests.

Counties are 1-degree squares laid out on a grid so that adjacent squares union
into a single polygon and non-adjacent squares union into a MultiPolygon. Real
geometries let the PostGIS Union / transform / area paths run for real.
"""

from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import MultiPolygon, Polygon

from django_omb_regions.models import WGS_SRID, County, State


def square(lon: float, lat: float, size: float = 1.0) -> MultiPolygon:
  """A size-degree square with its lower-left corner at (lon, lat)."""
  ring = Polygon(
    (
      (lon, lat),
      (lon + size, lat),
      (lon + size, lat + size),
      (lon, lat + size),
      (lon, lat),
    ),
    srid=WGS_SRID,
  )
  return MultiPolygon(ring, srid=WGS_SRID)


def make_state(
  fips2: str,
  name: str,
  postal_code: str,
  counties: list[tuple[str, str, float, float]],
) -> State:
  """Create a State and its counties from (fips3, name, lon, lat) tuples.

  The state shape is the union of its county shapes; sq_miles is computed from
  the real projection.
  """
  state = State.objects.create(
    fips2=fips2,
    code=f"{fips2}000",
    name=name,
    postal_code=postal_code,
    shape=square(0, 0),
    sq_miles=0.0,
  )
  for fips3, county_name, lon, lat in counties:
    county = County.objects.create(
      code=f"{fips2}{fips3}",
      fips2=fips2,
      fips3=fips3,
      name=county_name,
      postal_code=postal_code,
      shape=square(lon, lat),
      sq_miles=0.0,
      state=state,
    )
    county.set_sq_miles(save=True)

  shape = state.counties.aggregate(shape=Union("shape"))["shape"]
  if isinstance(shape, Polygon):
    shape = MultiPolygon(shape, srid=shape.srid)
  state.shape = shape
  state.set_sq_miles(save=True)
  return state
