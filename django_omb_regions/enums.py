from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class RegionCategory(TextChoices):
  """Leaf grains (STATE, COUNTY) plus the standard Census/OMB aggregations.

  Only the aggregation levels are valid ``Region.category`` values; STATE and
  COUNTY are included so the enum is a complete grain taxonomy. Downstream
  projects add their own categories via :func:`register_categories`.
  """

  STATE = "STATE", _("State")
  COUNTY = "COUNTY", _("County")
  USCBR = "USCBR", _("Census Bureau Region")
  USCBD = "USCBD", _("Census Bureau District")
  CSA = "CSA", _("Combined Statistical Area")
  MSA = "MSA", _("Metropolitan Statistical Area")
  MDIV = "MDIV", _("Metropolitan Division")
  MIC = "MIC", _("Micropolitan Statistical Area")

  # Library-derived, not official OMB geographies
  CSA_SP = "CSA_SP", _("Combined Statistical Area (State Portion)")
  MSA_SP = "MSA_SP", _("Metropolitan Statistical Area (State Portion)")
  MDIV_SP = "MDIV_SP", _("Metropolitan Division (State Portion)")
  MIC_SP = "MIC_SP", _("Micropolitan Statistical Area (State Portion)")

  @classmethod
  def delineated(cls) -> frozenset[RegionCategory]:
    """Categories whose regions are defined by an OMB delineation bulletin."""
    return frozenset(
      {
        cls.CSA,
        cls.MSA,
        cls.MDIV,
        cls.MIC,
        cls.CSA_SP,
        cls.MSA_SP,
        cls.MDIV_SP,
        cls.MIC_SP,
      }
    )

  @classmethod
  def is_delineated(cls, category: str) -> bool:
    return category in cls.delineated()


# Downstream-registered categories, keyed by code. Choices/admin only; category
# values never affect the database schema.
_EXTRA_CATEGORIES: dict[str, str] = {}


def register_categories(categories: type[TextChoices]) -> None:
  """Register a downstream project's categories, usually from AppConfig.ready()."""
  for value, label in categories.choices:
    _EXTRA_CATEGORIES[str(value)] = str(label)


def region_category_choices() -> list[tuple[str, str]]:
  """Valid ``Region.category`` choices: federal base plus registered extras."""
  excluded = {RegionCategory.STATE.value, RegionCategory.COUNTY.value}
  base = [
    (value, str(label))
    for value, label in RegionCategory.choices
    if value not in excluded
  ]
  return base + list(_EXTRA_CATEGORIES.items())


class DelineationBulletin(TextChoices):
  """OMB metropolitan-area delineation bulletins.

  Values use a uniform ``B{yy}{nn}`` token derived from the OMB bulletin
  number (``B1301`` == "OMB Bulletin No. 13-01"). The Census geo-variant M-codes
  (which were started in 2009) are noted per member for cross-reference:
  https://www.census.gov/programs-surveys/geography/guidance/geo-variants.html
  """

  NA = "NA", _("Not Applicable")
  B0304 = "B0304", _("OMB Bulletin No. 03-04, June 6, 2003")
  B1002 = "B1002", _("OMB Bulletin No. 10-02, December 1, 2009")  # M1
  B1301 = "B1301", _("OMB Bulletin No. 13-01, February 28, 2013")  # M2
  B1501 = "B1501", _("OMB Bulletin No. 15-01, July 15, 2015")  # M3
  B1701 = "B1701", _("OMB Bulletin No. 17-01, August 15, 2017")  # M4
  B1804 = "B1804", _("OMB Bulletin No. 18-04, September 14, 2018")  # M5
  B2001 = "B2001", _("OMB Bulletin No. 20-01, March 6, 2020")  # M6
  B2301 = "B2301", _("OMB Bulletin No. 23-01, July 21, 2023")  # M7

  @classmethod
  def get_current(cls) -> DelineationBulletin:
    """The most recent OMB delineation bulletin (newest last)."""
    return cls.B2301
