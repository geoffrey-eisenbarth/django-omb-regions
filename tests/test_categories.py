import pytest
from django.db.models import TextChoices

from django_omb_regions.enums import (
  DelineationBulletin,
  region_category_choices,
  register_categories,
)
from django_omb_regions.models import County, Region

pytestmark = pytest.mark.django_db


def test_registered_downstream_category_round_trips_on_region(grid):
  """A downstream category, once registered, is a usable Region.category.

  Choices are validation/display only, so the database stores the code and it
  round-trips without a migration.
  """

  class ParkCategory(TextChoices):
    PARK = "PARK", "Park Region"

  register_categories(ParkCategory)
  assert "PARK" in {code for code, _ in region_category_choices()}

  region = Region(
    code="700",
    category="PARK",
    name="Big Park",
    postal_code="TX",
    delineation_bulletin=DelineationBulletin.get_current(),
  )
  region.set_shape(County.objects.filter(code="48001"))
  region.set_sq_miles()
  region.save()
  region.counties.set(County.objects.filter(code="48001"))

  assert Region.objects.get(code="700").category == "PARK"
