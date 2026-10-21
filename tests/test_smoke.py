from omb_regions.constants import USA_FIPS, is_state_code
from omb_regions.enums import DelineationBulletin, Geography


def test_is_state_code():
  assert is_state_code("48000")
  assert not is_state_code(USA_FIPS)
  assert not is_state_code("48201")


def test_geography_region_choices_exclude_leaves():
  codes = {code for code, _ in Geography.regions}
  assert Geography.STATE not in codes
  assert Geography.COUNTY not in codes
  assert Geography.MSA in codes


def test_delineation_bulletin_has_current():
  assert DelineationBulletin.get_current() in set(DelineationBulletin)
