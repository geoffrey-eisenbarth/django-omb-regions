import pytest

from django_omb_regions.constants import USA_FIPS
from django_omb_regions.enums import DelineationBulletin
from django_omb_regions.models import County, Region
from django_omb_regions.resolvers import resolve_region_code, resolve_region_codes

pytestmark = pytest.mark.django_db

CURRENT = DelineationBulletin.get_current()
OLDER = DelineationBulletin.B2001
STATIC = DelineationBulletin.NA


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


def test_resolution_categories(grid):
  _make_region("900", Region.Category.MSA, ["48001", "48003"])

  resolved = resolve_region_codes([USA_FIPS, "48000", "900", "48001", "99999"])

  assert resolved[USA_FIPS].category == "NATION"
  assert resolved["48000"].category == "STATE"
  assert resolved["48000"].name == "Texas"
  assert resolved["900"].category == Region.Category.MSA
  assert resolved["48001"].category == "COUNTY"
  assert resolved["99999"].category == "UNKNOWN"


def test_region_resolution_uses_current_delineation(grid):
  # Same code in two bulletins; only the current one should resolve as a region.
  _make_region("950", Region.Category.MSA, ["48001"], bulletin=OLDER)

  assert resolve_region_code("950").category == "UNKNOWN"

  _make_region("950", Region.Category.MSA, ["48001"], bulletin=CURRENT)

  assert resolve_region_code("950").category == Region.Category.MSA


def test_region_code_colliding_with_county_resolves_as_region(grid):
  # A region whose code equals a county FIPS must win over the county match.
  _make_region("48001", Region.Category.MIC, ["48003"])

  resolved = resolve_region_code("48001")

  assert resolved.category == Region.Category.MIC
  assert isinstance(resolved.obj, Region)


def test_resolve_dedupes_repeated_codes(grid):
  resolved = resolve_region_codes(["48000", "48000", "48001"])

  assert set(resolved) == {"48000", "48001"}


def test_current_queryset_excludes_other_delineations(grid):
  _make_region("960", Region.Category.MSA, ["48001"], bulletin=CURRENT)
  _make_region("960", Region.Category.MSA, ["48001"], bulletin=OLDER)

  assert Region.objects.current().count() == 1
  assert Region.objects.count() == 2


def test_delineation_aware_filters(grid):
  _make_region("970", Region.Category.MSA, ["48001"], bulletin=CURRENT)
  _make_region("970", Region.Category.MSA, ["48001"], bulletin=OLDER)
  _make_region("R1", Region.Category.USCBR, ["48001"], bulletin=STATIC)

  current = set(Region.objects.current().values_list("code", flat=True))
  static = set(Region.objects.static().values_list("code", flat=True))
  both = set(Region.objects.current_or_static().values_list("code", flat=True))

  assert current == {"970"}
  assert static == {"R1"}
  assert both == {"970", "R1"}
  assert Region.objects.current(category=Region.Category.MSA).count() == 1
