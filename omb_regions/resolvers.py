from dataclasses import dataclass
from typing import TYPE_CHECKING

from omb_regions.constants import USA_FIPS, is_state_code
from omb_regions.models import County, Region, State

if TYPE_CHECKING:
  from collections.abc import Iterable


@dataclass(frozen=True)
class Geography:
  code: str
  name: str
  category: str
  obj: State | County | Region | None = None

  def __str__(self) -> str:
    return str(self.obj)

  @property
  def is_state(self) -> bool:
    return self.category == "STATE"

  @property
  def is_metro(self) -> bool:
    return self.category in {
      Region.Category.MSA,
      Region.Category.MDIV,
      Region.Category.MIC,
      Region.Category.FROST,
    }

  @property
  def is_county(self) -> bool:
    return self.category == "COUNTY"


def resolve_region_codes(
  region_codes: Iterable[str],
) -> dict[str, Geography]:
  """Resolve economic-data region codes to Geography in bulk.

  Performs at most one query per geography table. Resolution priority:
  NATION -> State aggregate (NN000) -> current Region -> County -> UNKNOWN.
  """
  codes = list(dict.fromkeys(region_codes))

  state_codes = [code for code in codes if is_state_code(code)]
  other_codes = [code for code in codes if code != USA_FIPS and not is_state_code(code)]

  states = State.objects.in_bulk(state_codes, field_name="code")
  regions = {
    region.code: region for region in Region.current.filter(code__in=other_codes)
  }
  county_codes = [code for code in other_codes if code not in regions]
  counties = County.objects.in_bulk(county_codes, field_name="code")

  geographies = {code: _resolve(code, states, regions, counties) for code in codes}
  return geographies


def resolve_region_code(region_code: str) -> Geography:
  """Resolve a single economic-data region code to a Geography."""
  return resolve_region_codes([region_code])[region_code]


def _resolve(
  code: str,
  states: dict[str, State],
  regions: dict[str, Region],
  counties: dict[str, County],
) -> Geography:
  geography = Geography(code=code, name=code, category="UNKNOWN")

  if code == USA_FIPS:
    geography = Geography(
      code=code,
      name="United States",
      category="NATION",
    )
  elif is_state_code(code) and (state := states.get(code)):
    geography = Geography(
      code=code,
      name=state.name,
      category="STATE",
      obj=state,
    )
  elif region := regions.get(code):
    geography = Geography(
      code=code,
      name=region.name,
      category=region.category,
      obj=region,
    )
  elif county := counties.get(code):
    geography = Geography(
      code=code,
      name=county.name,
      category="COUNTY",
      obj=county,
    )

  return geography
