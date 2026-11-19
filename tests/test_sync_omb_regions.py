import pytest

from django_omb_regions.enums import DelineationBulletin
from django_omb_regions.management.commands.sync_omb_regions import (
  Command,
  OmbRegionRecord,
)
from django_omb_regions.models import Region

pytestmark = pytest.mark.django_db

CURRENT = DelineationBulletin.get_current()


def _record(code, category, county_codes):
  return OmbRegionRecord(
    delineation_bulletin=CURRENT,
    code=code,
    name=f"Region {code}",
    postal_code="TX-NM",
    category=category,
    county_code=tuple(county_codes),
  )


def test_multistate_region_gets_one_state_portion_per_state(grid):
  record = _record("19100", Region.Category.MSA, ["48001", "48003", "35001"])

  Command()._upsert([record], missing_only=False)

  tx_portion = Region.objects.get(code="19100TX")
  nm_portion = Region.objects.get(code="19100NM")
  assert tx_portion.category == Region.Category.MSA_SP
  assert set(tx_portion.counties.values_list("code", flat=True)) == {
    "48001",
    "48003",
  }
  assert nm_portion.category == Region.Category.MSA_SP
  assert set(nm_portion.counties.values_list("code", flat=True)) == {"35001"}
  assert tx_portion.name == record.name
  assert tx_portion.postal_code == "TX"


def test_single_state_region_gets_no_state_portions(grid):
  record = _record("900", Region.Category.MSA, ["48001", "48003"])

  Command()._upsert([record], missing_only=False)

  assert not Region.objects.filter(code__startswith="900").exclude(code="900").exists()


def test_csa_derives_csa_sp_portions(grid):
  record = _record("206", Region.Category.CSA, ["48001", "35001"])

  Command()._upsert([record], missing_only=False)

  assert Region.objects.get(code="206TX").category == Region.Category.CSA_SP
  assert Region.objects.get(code="206NM").category == Region.Category.CSA_SP


def test_split_name_and_postal_code_standard_form():
  name, postal_code = Command()._split_name_and_postal_code("Texarkana, TX-AR")
  assert name == "Texarkana"
  assert postal_code == "TX-AR"


def test_split_name_and_postal_code_mayaguez_special_case():
  name, postal_code = Command()._split_name_and_postal_code(
    "Mayagüez-San Germán-Cabo Rojo"
  )
  assert name == "Mayagüez-San Germán-Cabo Rojo"
  assert postal_code == "PR"


def test_split_name_and_postal_code_legacy_texarkana_duplicate_name():
  # The 2003/2009 bulletins title this CBSA "Texarkana, TX-Texarkana, AR"
  # instead of the usual "Texarkana, TX-AR".
  name, postal_code = Command()._split_name_and_postal_code(
    "Texarkana, TX-Texarkana, AR"
  )
  assert name == "Texarkana"
  assert postal_code == "TX-AR"


def test_split_name_and_postal_code_raises_on_unexpected_multiple_commas():
  with pytest.raises(ValueError, match="Could not split"):
    Command()._split_name_and_postal_code("Springfield, MO-Chicago, IL")


def test_rerun_updates_existing_state_portions(grid):
  record = _record("19100", Region.Category.MSA, ["48001", "35001"])
  Command()._upsert([record], missing_only=False)

  grown = _record("19100", Region.Category.MSA, ["48001", "48003", "35001"])
  Command()._upsert([grown], missing_only=False)

  tx_portion = Region.objects.get(code="19100TX")
  assert set(tx_portion.counties.values_list("code", flat=True)) == {
    "48001",
    "48003",
  }
