from django.db.models import TextChoices
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy as _


class Geography(TextChoices):
  """Types of geographic unit spanning State, County, and Region.

  The US Census refers to these as "geographies". Members include the two
  leaf models (``STATE``, ``COUNTY``) as well as every ``Region`` aggregation
  level. Only the aggregation levels are valid values for ``Region.category``
  (see :attr:`regions`); ``STATE`` and ``COUNTY`` are included so the enum can
  serve as a complete taxonomy for dataset grain, regroup targets, etc.
  """

  STATE = "STATE", _("State")
  COUNTY = "COUNTY", _("County")
  USCBR = "USCBR", _("Census Bureau Region")
  USCBD = "USCBD", _("Census Bureau District")
  BASIN = "BASIN", _("Petroleum Basin")
  URBAN = "URBAN", _("Urban")
  RURAL = "RURAL", _("Rural")
  TOURISM = "TOURISM", _("Tourism Region")
  EDR = "EDR", _("Economic Development Region")
  EPR = "EPR", _("Economic Planning Region")
  COG = "COG", _("Council of Governments Region")
  WDA = "WDA", _("Workforce Development Area")
  FROST = "FROST", _("Frost Bank Region")
  CSA = "CSA", _("Combined Statistical Area")
  MSA = "MSA", _("Metropolitan Statistical Area")
  MDIV = "MDIV", _("Metropolitan Division")
  MIC = "MIC", _("Micropolitan Statistical Area")
  DOTD = "DOTD", _("Department of Transportation District")
  USDC = "USDC", _("United States District Court")
  USDCD = "USDCD", _("United States District Court Division")
  SHD = "SHD", _("State House of Representatives District")
  SSD = "SSD", _("State Senate District")
  USCD = "USCD", _("United States Congressional District")
  SBED = "SBED", _("State Board of Education District")
  TPG = "TPG", _("Perryman Group Study Region")

  @classproperty
  def covers(cls) -> frozenset[Geography]:
    return frozenset({cls.TOURISM, cls.EPR, cls.COG, cls.WDA})

  @classmethod
  def is_covering(cls, category: str) -> bool:
    return category in cls.covers

  @classproperty
  def regions(cls) -> list[tuple[str, str]]:
    """Choices valid as a ``Region.category`` (excludes STATE and COUNTY)."""
    excluded = {Geography.STATE.value, Geography.COUNTY.value}
    return [
      (value, str(label)) for value, label in Geography.choices if value not in excluded
    ]


class DelineationBulletin(TextChoices):
  """OMB metropolitan-area delineation bulletins.

  Values use a uniform ``B{yy}{nn}`` token derived from the OMB bulletin
  number (``B1301`` == "OMB Bulletin No. 13-01").  This agency-neutral key is
  shared by every dataset that carries a metro geography -- Census (CBP/EC/
  NES), BLS (QCEW) and BEA (REIS/GDP) -- because each agency's metropolitan
  definitions trace to the same OMB bulletin, not to any one agency's own
  labels.  The Census geo-variant M-codes (M1..M7, which only exist from 2009)
  are noted per member for cross-reference:
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
