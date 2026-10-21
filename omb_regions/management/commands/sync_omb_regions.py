import io
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd
import requests
from django.core.management.base import CommandError
from django.db import transaction

from omb_regions.enums import DelineationBulletin
from omb_regions.management.commands._region_sync_base import RegionSyncBaseCommand  # noqa: E501
from omb_regions.management.commands._sync_base import SyncSummary
from omb_regions.models import County, Region

if TYPE_CHECKING:
  from typing import Any


#: OMB delineation reference files keyed by bulletin.  The 2003 file is the
#: December 2003 tabulation of the first (2000-standard) CBSAs; 2013 onward are
#: the standard ``list1`` delineation files.
DELINEATION_FILES = {
  DelineationBulletin.B0304: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2003/historical-delineation-files/0312cbsas-csas.xls",  # noqa: E501
  DelineationBulletin.B1301: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2013/delineation-files/list1.xls",  # noqa: E501
  DelineationBulletin.B1501: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2015/delineation-files/list1.xls",  # noqa: E501
  DelineationBulletin.B1701: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2017/delineation-files/list1.xls",  # noqa: E501
  DelineationBulletin.B1804: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2018/delineation-files/list1_Sep_2018.xls",  # noqa: E501
  DelineationBulletin.B2001: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2020/delineation-files/list1_2020.xls",  # noqa: E501
  DelineationBulletin.B2301: "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx",  # noqa: E501
}

#: Bulletins whose reference files predate the single-sheet ``list1`` layout
#: and are instead published as fixed-width text: ``list1`` (CBSA + division
#: components down to county) plus ``list6`` (CSA -> component CBSA).  ``B1002``
#: (the December 2009 tabulation) is the delineation the 2007 Economic Census
#: and 2007-2011 Nonemployer Statistics tabulate; its CSAs add counties to the
#: 2003 footprint (e.g. Dallas-Fort Worth CSA 206 gains Fannin and Grayson,
#: still Texas-only) that the 2003 snapshot lacks.
LEGACY_DELINEATION_FILES = {
  DelineationBulletin.B1002: {
    "components": "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2009/historical-delineation-files/list1.txt",  # noqa: E501
    "combined": "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2009/historical-delineation-files/list6.txt",  # noqa: E501
  },
}

#: Every bulletin this command can sync, modern or legacy.
ALL_DELINEATION_FILES = {**DELINEATION_FILES, **LEGACY_DELINEATION_FILES}

#: Fixed-width column offsets in the legacy ``list1`` components file: 5-digit
#: CBSA code, 5-digit metropolitan-division code, 5-digit county FIPS, then the
#: title.  A row with a county FIPS is a component; a row with only a CBSA (or
#: CBSA + division) code and a title is a header carrying the name and level.
_LEGACY_L1_CBSA = slice(0, 5)
_LEGACY_L1_DIVISION = slice(8, 13)
_LEGACY_L1_COUNTY = slice(16, 21)
_LEGACY_L1_TITLE = slice(21, None)

#: Fixed-width column offsets in the legacy ``list6`` combined file: 3-digit
#: CSA code, 5-digit component CBSA code, then the title.  A row with no CBSA
#: code is the CSA header carrying its name.
_LEGACY_L6_CSA = slice(0, 3)
_LEGACY_L6_CBSA = slice(5, 10)
_LEGACY_L6_TITLE = slice(10, None)

#: Title suffixes that identify a legacy header row's level.
_LEGACY_LEVELS = {
  " Metropolitan Statistical Area": "Metropolitan Statistical Area",
  " Micropolitan Statistical Area": "Micropolitan Statistical Area",
}
_LEGACY_DIVISION_SUFFIX = " Metropolitan Division"
_LEGACY_CSA_SUFFIX = " Combined Statistical Area"

CATEGORY_BY_LABEL = {
  "Metropolitan Statistical Area": Region.Category.MSA,
  "Micropolitan Statistical Area": Region.Category.MIC,
}


@dataclass(frozen=True)
class OmbRegionSource:
  delineation_bulletin: DelineationBulletin
  dataframe: pd.DataFrame


@dataclass(frozen=True)
class OmbRegionRecord:
  delineation_bulletin: DelineationBulletin
  code: str
  name: str
  postal_code: str
  category: str
  county_code: tuple[str, ...]


class Command(RegionSyncBaseCommand):
  help = "Downloads and syncs OMB metropolitan region definitions."

  sync_noun = "OMB regions"

  def add_arguments(self, parser: Any) -> None:
    parser.add_argument(
      "--category",
      type=str,
      choices=[
        Region.Category.CSA,
        Region.Category.MSA,
        Region.Category.MIC,
        Region.Category.MDIV,
      ],
      help="Optional OMB region category to sync.",
    )
    parser.add_argument(
      "--bulletin",
      type=str,
      choices=[bulletin.value for bulletin in ALL_DELINEATION_FILES],
      help="OMB delineation bulletin to sync, e.g. B1501. Omit to sync all.",
    )
    self.add_missing_only_argument(parser)

  def handle(self, *args: Any, **options: Any) -> None:
    source_data = self._fetch(
      bulletin=options.get("bulletin"),
    )
    records = self._build_records(
      source_data,
      category=options.get("category"),
    )
    summary = self._upsert(
      records,
      missing_only=options["missing_only"],
    )
    self._sync_relationships(records)
    self._report_summary(summary)

  def _fetch(
    self,
    *,
    bulletin: str | None,
  ) -> list[OmbRegionSource]:
    self.stdout.write("Fetching OMB region definitions...")

    bulletins = self._get_bulletins(bulletin=bulletin)
    sources: list[OmbRegionSource] = []
    for delineation_bulletin in bulletins:
      if delineation_bulletin in LEGACY_DELINEATION_FILES:
        dataframe = self._fetch_legacy(delineation_bulletin)
      else:
        url = DELINEATION_FILES[delineation_bulletin]
        response = requests.get(url, timeout=(10, 120))
        response.raise_for_status()
        dataframe = pd.read_excel(io.BytesIO(response.content), skiprows=2)
      sources.append(
        OmbRegionSource(
          delineation_bulletin=delineation_bulletin,
          dataframe=dataframe,
        )
      )

    return sources

  def _fetch_legacy(
    self,
    bulletin: DelineationBulletin,
  ) -> pd.DataFrame:
    """Parse a pre-``list1`` fixed-width delineation into the modern shape.

    The 2009 tabulation ships as two fixed-width text files: ``list1`` maps
    each CBSA (and metropolitan division) down to its component counties, and
    ``list6`` maps each CSA to its component CBSAs.  This joins them into the
    one-county-per-row frame ``_build_records`` expects, with the same column
    names the single-sheet ``list1`` Excel files carry.
    """
    urls = LEGACY_DELINEATION_FILES[bulletin]
    components = requests.get(urls["components"], timeout=(10, 120))
    components.raise_for_status()
    combined = requests.get(urls["combined"], timeout=(10, 120))
    combined.raise_for_status()

    df = self._parse_legacy_components(components.text)
    csa_titles, cbsa_to_csa = self._parse_legacy_combined(combined.text)
    df["CSA Code"] = df["CBSA Code"].map(cbsa_to_csa)
    df["CSA Title"] = df["CSA Code"].map(
      lambda code: csa_titles.get(code) if code else None
    )
    return df

  def _parse_legacy_components(self, text: str) -> pd.DataFrame:
    """Parse the fixed-width ``list1`` file into one row per (CBSA, county)."""
    cbsa_titles: dict[str, str] = {}
    cbsa_levels: dict[str, str] = {}
    division_titles: dict[str, str] = {}
    rows: list[tuple[str, str | None, str]] = []
    for line in text.splitlines():
      code = line[_LEGACY_L1_CBSA].strip()
      if not code.isdigit():
        continue
      division = line[_LEGACY_L1_DIVISION].strip()
      county = line[_LEGACY_L1_COUNTY].strip()
      title = line[_LEGACY_L1_TITLE].strip()
      if county:
        rows.append((code, division or None, county))
      elif division:
        if title.endswith(_LEGACY_DIVISION_SUFFIX):
          division_titles[division] = title[: -len(_LEGACY_DIVISION_SUFFIX)]
      else:
        for suffix, level in _LEGACY_LEVELS.items():
          if title.endswith(suffix):
            cbsa_levels[code] = level
            cbsa_titles[code] = title[: -len(suffix)]
            break

    df = pd.DataFrame(
      rows,
      columns=["CBSA Code", "Metropolitan Division Code", "full_code"],
    )
    df["CBSA Title"] = df["CBSA Code"].map(cbsa_titles)
    df["Metropolitan/Micropolitan Statistical Area"] = df["CBSA Code"].map(cbsa_levels)
    df["Metropolitan Division Title"] = df["Metropolitan Division Code"].map(
      division_titles
    )
    return df

  def _parse_legacy_combined(
    self,
    text: str,
  ) -> tuple[dict[str, str], dict[str, str]]:
    """Parse the fixed-width ``list6`` file into CSA titles and CBSA->CSA."""
    csa_titles: dict[str, str] = {}
    cbsa_to_csa: dict[str, str] = {}
    for line in text.splitlines():
      csa = line[_LEGACY_L6_CSA].strip()
      if not csa.isdigit():
        continue
      cbsa = line[_LEGACY_L6_CBSA].strip()
      title = line[_LEGACY_L6_TITLE].strip()
      if cbsa:
        cbsa_to_csa[cbsa] = csa
      elif title.endswith(_LEGACY_CSA_SUFFIX):
        csa_titles[csa] = title[: -len(_LEGACY_CSA_SUFFIX)]
    return csa_titles, cbsa_to_csa

  def _build_records(
    self,
    source_data: list[OmbRegionSource],
    *,
    category: str | None,
  ) -> list[OmbRegionRecord]:
    self.stdout.write("Normalizing OMB region records...")

    records: list[OmbRegionRecord] = []
    for source in source_data:
      df = self._normalize_census_cbsa_dataframe(source.dataframe)
      self._validate_census_cbsa_dataframe(
        df, delineation_bulletin=source.delineation_bulletin
      )
      df = df[df["CBSA Code"].notna() & df["full_code"].notna()].copy()

      for label, group in df.groupby("Metropolitan/Micropolitan Statistical Area"):  # noqa: E501
        record_category = CATEGORY_BY_LABEL.get(str(label))
        if record_category is None or (category and category != record_category):  # noqa: E501
          continue
        for (code, name), cbsa in group.groupby(
          [
            "CBSA Code",
            "CBSA Title",
          ]
        ):
          region_name, postal_code = self._split_name_and_postal_code(name)
          records.append(
            OmbRegionRecord(
              delineation_bulletin=source.delineation_bulletin,
              code=str(code).strip(),
              name=region_name,
              postal_code=postal_code,
              category=record_category,
              county_code=tuple(sorted(set(cbsa["full_code"].tolist()))),
            )
          )

      if category in [None, Region.Category.CSA]:
        csa_df = df[df["CSA Code"].notna()]
        for (code, name), group in csa_df.groupby(
          [
            "CSA Code",
            "CSA Title",
          ]
        ):
          region_name, postal_code = self._split_name_and_postal_code(name)
          records.append(
            OmbRegionRecord(
              delineation_bulletin=source.delineation_bulletin,
              code=str(code).strip(),
              name=region_name,
              postal_code=postal_code,
              category=Region.Category.CSA,
              county_code=tuple(sorted(set(group["full_code"].tolist()))),
            )
          )

      if category in [None, Region.Category.MDIV]:
        division_df = df[df["Metropolitan Division Code"].notna()]
        for (code, name), group in division_df.groupby(
          [
            "Metropolitan Division Code",
            "Metropolitan Division Title",
          ]
        ):
          region_name, postal_code = self._split_name_and_postal_code(name)
          records.append(
            OmbRegionRecord(
              delineation_bulletin=source.delineation_bulletin,
              code=str(code).strip(),
              name=region_name,
              postal_code=postal_code,
              category=Region.Category.MDIV,
              county_code=tuple(sorted(set(group["full_code"].tolist()))),
            )
          )

    records = sorted(
      records,
      key=lambda record: (
        record.delineation_bulletin.value,
        record.category,
        record.code,
      ),
    )
    return records

  def _upsert(
    self,
    records: list[OmbRegionRecord],
    *,
    missing_only: bool,
  ) -> SyncSummary:
    self.stdout.write("Syncing OMB regions...")

    summary = SyncSummary()
    with transaction.atomic():
      for record in records:
        counties = list(County.objects.filter(code__in=record.county_code))
        found_codes = {county.code for county in counties}
        missing_codes = sorted(set(record.county_code) - found_codes)
        if missing_codes:
          self._warn_missing_counties(record, counties, missing_codes)
          summary.skipped += 1
          continue
        was_created, was_skipped = self._upsert_region(
          code=record.code,
          name=record.name,
          postal_code=record.postal_code,
          category=record.category,
          delineation_bulletin=record.delineation_bulletin,
          counties=counties,
          missing_only=missing_only,
        )
        if was_skipped:
          summary.skipped += 1
        elif was_created:
          summary.created += 1
        else:
          summary.updated += 1

    return summary

  def _warn_missing_counties(
    self,
    record: OmbRegionRecord,
    counties: list[County],
    missing_codes: list[str],
  ) -> None:
    county_details = (
      ", ".join(
        f"{county.name} ({county.code})"
        for county in sorted(counties, key=lambda county: county.code)
      )
      or "none"
    )
    warnings.warn(
      (
        f"Skipping {record.name} [{record.code}] for "
        f"{record.delineation_bulletin.value} because TIGER county "
        f"coverage is incomplete. "
        f"Found counties: {county_details}. "
        f"Missing county codes: {', '.join(missing_codes)}."
      ),
      stacklevel=2,
    )

  def _sync_relationships(self, records: list[OmbRegionRecord]) -> None:
    self.stdout.write("Syncing OMB region relationships...")

  def _normalize_census_cbsa_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    rename_columns = {
      "Metro Division Code": "Metropolitan Division Code",
      "Level of CBSA": "Metropolitan/Micropolitan Statistical Area",
    }
    df = df.rename(
      columns={
        old: new for old, new in rename_columns.items() if old in df and new not in df
      }
    )

    for code_column in ["CBSA Code", "Metropolitan Division Code"]:
      if code_column in df:
        df[code_column] = df[code_column].map(self._format_code)

    if "CSA Code" in df:
      df["CSA Code"] = df["CSA Code"].map(
        lambda value: self._format_code(value, width=3)
      )

    if "full_code" not in df:
      if "FIPS" in df:
        df["full_code"] = df["FIPS"].map(self._format_code)
      elif {"FIPS State Code", "FIPS County Code"} <= set(df.columns):
        df["full_code"] = df["FIPS State Code"].map(self._format_code, width=2) + df[
          "FIPS County Code"
        ].map(self._format_code, width=3)

    return df

  def _validate_census_cbsa_dataframe(
    self,
    df: pd.DataFrame,
    *,
    delineation_bulletin: DelineationBulletin,
  ) -> None:
    required_columns = [
      "CBSA Code",
      "CBSA Title",
      "CSA Code",
      "CSA Title",
      "Metropolitan/Micropolitan Statistical Area",
      "Metropolitan Division Code",
      "Metropolitan Division Title",
      "full_code",
    ]
    missing_columns = [c for c in required_columns if c not in df]
    if missing_columns:
      raise CommandError(
        "Census delineation file is missing columns for "
        f"{delineation_bulletin.value}: {', '.join(missing_columns)}"
      )

  def _get_bulletins(
    self,
    *,
    bulletin: str | None,
  ) -> list[DelineationBulletin]:
    if bulletin:
      bulletins = [DelineationBulletin(bulletin)]
    else:
      bulletins = sorted(
        ALL_DELINEATION_FILES,
        key=lambda candidate: candidate.value,
      )

    invalid = [
      candidate for candidate in bulletins if candidate not in ALL_DELINEATION_FILES
    ]
    if invalid:
      raise CommandError(
        "No OMB delineation file configured for: "
        f"{', '.join(candidate.value for candidate in invalid)}"
      )
    if not bulletins:
      raise CommandError("No OMB delineation bulletin configured.")

    return bulletins

  def _format_code(
    self,
    value: Any,
    width: int = 5,
  ) -> str | None:
    try:
      return f"{int(value):0{width}d}"
    except ValueError, TypeError:
      return None

  def _split_name_and_postal_code(self, value: Any) -> tuple[str, str]:
    raw_name = str(value).strip()
    try:
      name, postal_code = raw_name.rsplit(", ", 1)
    except ValueError:
      if raw_name != "Mayagüez-San Germán-Cabo Rojo":
        raise
      name = raw_name
      postal_code = "PR"
    return name, postal_code
