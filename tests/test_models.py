import pytest
from django.db import IntegrityError

from django_omb_regions.enums import DelineationBulletin
from django_omb_regions.models import County, Region

pytestmark = pytest.mark.django_db

CURRENT = DelineationBulletin.get_current()


def _make_region(code, category, county_codes, bulletin=CURRENT):
  counties = County.objects.filter(code__in=county_codes)
  region = Region(
    code=code,
    category=category,
    name=f"Region {code}",
    postal_code="TX",
    delineation_bulletin=bulletin,
  )
  region.set_shape(counties)
  region.set_sq_miles()
  region.save()
  region.counties.set(counties)
  return region


def test_set_shape_unions_adjacent_counties_into_single_polygon(grid):
  region = _make_region("900", Region.Category.MSA, ["48001", "48003"])

  # Adjacent squares dissolve into one contiguous polygon.
  assert region.shape.geom_type == "MultiPolygon"
  assert region.shape.num_geom == 1


def test_set_shape_keeps_noncontiguous_counties_as_multipolygon(grid):
  region = _make_region("910", Region.Category.CSA, ["48001", "35003"])

  assert region.shape.num_geom == 2


def test_set_shape_without_counties_raises(grid):
  region = Region(
    code="999",
    category=Region.Category.MSA,
    name="Empty",
    postal_code="TX",
    delineation_bulletin=CURRENT,
  )
  with pytest.raises(ValueError):
    region.set_shape(County.objects.none())


def test_sq_miles_is_realistic_and_additive_and_preserves_srid(grid):
  region = _make_region("900", Region.Category.MSA, ["48001", "48003"])
  counties = County.objects.filter(code__in=["48001", "48003"])

  # Two 1-degree squares near 31 degrees N are ~4,000 sq mi each.
  assert 6000 < region.sq_miles < 10000
  county_total = sum(county.sq_miles for county in counties)
  assert region.sq_miles == pytest.approx(county_total, rel=0.01)
  # The equal-area transform must not mutate the stored WGS84 shape.
  assert region.shape.srid == 4326


def test_is_metro_depends_on_category(grid):
  metro = _make_region("900", Region.Category.MSA, ["48001"])
  census = _make_region("R3", Region.Category.USCBR, ["48003"])

  assert metro.is_metro
  assert not census.is_metro


def test_unique_code_per_delineation_bulletin(grid):
  _make_region("900", Region.Category.MSA, ["48001"])
  with pytest.raises(IntegrityError):
    Region.objects.create(
      code="900",
      category=Region.Category.MSA,
      name="Duplicate",
      postal_code="TX",
      delineation_bulletin=CURRENT,
      shape=County.objects.get(code="48003").shape,
      sq_miles=1.0,
    )
