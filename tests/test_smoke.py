from django_omb_regions.constants import USA_FIPS, is_state_code
from django_omb_regions.enums import (
  DelineationBulletin,
  RegionCategory,
  region_category_choices,
  register_categories,
)


def test_is_state_code():
  assert is_state_code("48000")
  assert not is_state_code(USA_FIPS)
  assert not is_state_code("48201")


def test_region_category_choices_exclude_leaves():
  codes = {code for code, _ in region_category_choices()}
  assert RegionCategory.STATE not in codes
  assert RegionCategory.COUNTY not in codes
  assert RegionCategory.MSA in codes


def test_register_categories_extends_choices():
  from django.db.models import TextChoices

  class ExtraCategory(TextChoices):
    WIDGET = "WIDGET", "Widget Region"

  register_categories(ExtraCategory)
  codes = {code for code, _ in region_category_choices()}
  assert "WIDGET" in codes


def test_delineation_bulletin_has_current():
  assert DelineationBulletin.get_current() in set(DelineationBulletin)
