from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.management.base import CommandError
from django.db import transaction

from omb_regions import defs
from omb_regions.enums import DelineationBulletin
from omb_regions.management.commands._region_sync_base import RegionSyncBaseCommand  # noqa: E501
from omb_regions.management.commands._sync_base import SyncSummary
from omb_regions.models import County, Region

if TYPE_CHECKING:
  from typing import Any


@dataclass(frozen=True)
class RegionComponent:
  code: str
  name: str


@dataclass(frozen=True)
class StaticRegionRecord:
  code: str
  name: str
  postal_code: str
  category: str
  delineation_bulletin: DelineationBulletin
  components: tuple[RegionComponent, ...]


class Command(RegionSyncBaseCommand):
  help = "Syncs curated static region definitions."

  sync_noun = "static regions"

  def add_arguments(self, parser: Any) -> None:
    parser.add_argument(
      "--category",
      type=str,
      help="Optional static region category to sync.",
    )
    parser.add_argument(
      "--bulletin",
      type=str,
      help="OMB delineation bulletin for the default delineation, e.g. B2301.",
    )
    self.add_missing_only_argument(parser)

  def handle(self, *args: Any, **options: Any) -> None:
    source_data = self._fetch(
      category=options.get("category"),
      bulletin=options.get("bulletin"),
    )
    records = self._build_records(source_data)
    summary = self._upsert(records, missing_only=options["missing_only"])
    self._sync_relationships(records)
    self._report_summary(summary)

  def _fetch(
    self,
    *,
    category: str | None,
    bulletin: str | None,
  ) -> list[dict[str, Any]]:
    self.stdout.write("Fetching static region definitions...")

    default_delineation_bulletin = self._get_default_delineation_bulletin(
      bulletin=bulletin,
    )
    source_data = [
      {
        **record,
        "default_delineation_bulletin": default_delineation_bulletin,
      }
      for record in defs.REGIONS
      if category is None or record["category"] == category
    ]
    return source_data

  def _build_records(
    self,
    source_data: list[dict[str, Any]],
  ) -> list[StaticRegionRecord]:
    self.stdout.write("Normalizing static region records...")

    records = [self._parse_static_region_record(record) for record in source_data]
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
    records: list[StaticRegionRecord],
    *,
    missing_only: bool,
  ) -> SyncSummary:
    self.stdout.write("Syncing static regions...")

    summary = SyncSummary()
    existing_keys = set(
      Region.versions.filter(
        code__in=[record.code for record in records],
        delineation_bulletin__in=[record.delineation_bulletin for record in records],
      ).values_list("code", "delineation_bulletin")
    )
    pending = list(records)

    with transaction.atomic():
      while pending:
        progressed = False
        for record in list(pending):
          record_key = (record.code, record.delineation_bulletin)
          if missing_only and record_key in existing_keys:
            summary.skipped += 1
            pending.remove(record)
            progressed = True
            continue

          counties = self._resolve_counties_from_components(
            record.components,
            record.delineation_bulletin,
          )
          if counties is None:
            continue

          was_created, was_skipped = self._upsert_region(
            code=record.code,
            name=record.name,
            postal_code=record.postal_code,
            category=record.category,
            delineation_bulletin=record.delineation_bulletin,
            counties=counties,
            missing_only=False,
          )
          pending.remove(record)
          progressed = True
          if was_skipped:
            summary.skipped += 1
          elif was_created:
            summary.created += 1
          else:
            summary.updated += 1

        if not progressed:
          unresolved_codes = ", ".join(record.code for record in pending)
          guidance = ""
          if self._has_omb_dependencies(pending):
            guidance = " Run sync_omb_regions first."
          raise CommandError(
            f"Could not resolve static regions: {unresolved_codes}.{guidance}"
          )

    return summary

  def _sync_relationships(self, records: list[StaticRegionRecord]) -> None:
    self.stdout.write("Syncing static region relationships...")

  def _parse_static_region_record(
    self,
    row: dict[str, Any],
  ) -> StaticRegionRecord:
    raw_bulletin = row.get("delineation_bulletin")
    if raw_bulletin is None:
      delineation_bulletin = row["default_delineation_bulletin"]
    else:
      delineation_bulletin = DelineationBulletin(raw_bulletin)

    raw_components = row.get("components")
    if not raw_components:
      raise CommandError(f"Static region {row['code']} must define components.")
    if "postal_code" not in row:
      raise CommandError(f"Static region {row['code']} must define postal_code.")
    components = tuple(
      RegionComponent(code=code, name=name) for code, name in raw_components
    )

    return StaticRegionRecord(
      code=str(row["code"]),
      name=str(row["name"]).strip(),
      postal_code=str(row["postal_code"]).strip(),
      category=str(row["category"]),
      delineation_bulletin=delineation_bulletin,
      components=components,
    )

  def _get_default_delineation_bulletin(
    self,
    *,
    bulletin: str | None,
  ) -> DelineationBulletin:
    if bulletin:
      return DelineationBulletin(bulletin)
    return DelineationBulletin.get_current()

  def _resolve_counties_from_components(
    self,
    components: tuple[RegionComponent, ...],
    delineation_bulletin: DelineationBulletin,
  ) -> list[County] | None:
    codes = [component.code for component in components]
    counties = self._resolve_counties_from_codes(codes, delineation_bulletin)
    return counties

  def _has_omb_dependencies(self, records: list[StaticRegionRecord]) -> bool:
    has_dependency = False
    for record in records:
      if any(
        len(component.code) == 5
        and component.code.isdigit()
        and not component.code.endswith("000")
        and not County.objects.filter(code=component.code).exists()
        for component in record.components
      ):
        has_dependency = True
        break

    return has_dependency
