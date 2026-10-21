from typing import TYPE_CHECKING

from django.core.management.base import CommandError

from omb_regions.constants import is_state_code
from omb_regions.management.commands._sync_base import SyncBaseCommand
from omb_regions.models import County, Region

if TYPE_CHECKING:
  from collections.abc import Sequence

  from omb_regions.enums import DelineationBulletin


class RegionSyncBaseCommand(SyncBaseCommand):
  def _upsert_region(
    self,
    *,
    code: str,
    name: str,
    postal_code: str,
    category: str,
    delineation_bulletin: DelineationBulletin,
    counties: Sequence[County],
    missing_only: bool = False,
  ) -> tuple[bool, bool]:
    if not counties:
      raise CommandError(f"Region {code} has no counties.")

    region_exists = Region.versions.filter(
      code=code,
      delineation_bulletin=delineation_bulletin,
    ).exists()
    if missing_only and region_exists:
      was_created = False
      was_skipped = True
    else:
      counties_qs = County.objects.filter(pk__in=[county.pk for county in counties])
      region = Region(
        code=code,
        category=category,
        name=name,
        postal_code=postal_code,
        delineation_bulletin=delineation_bulletin,
      )
      region.set_shape(counties_qs)
      region.set_sq_miles()

      region, was_created = Region.versions.update_or_create(
        code=region.code,
        delineation_bulletin=delineation_bulletin,
        defaults={
          "category": region.category,
          "name": region.name,
          "postal_code": region.postal_code,
          "shape": region.shape,
          "sq_miles": region.sq_miles,
        },
      )
      region.counties.set(counties)
      was_skipped = False

    return was_created, was_skipped

  def _resolve_counties_from_codes(
    self,
    codes: Sequence[str],
    delineation_bulletin: DelineationBulletin,
  ) -> list[County] | None:
    counties = {}

    for code in codes:
      if region := Region.versions.filter(
        code=code,
        delineation_bulletin=delineation_bulletin,
      ).first():
        counties.update({county.pk: county for county in region.counties.all()})

      elif county := County.objects.filter(code=code).first():
        counties[county.pk] = county

      elif is_state_code(code):
        state_counties = County.objects.filter(state__code=code)
        if state_counties.exists():
          counties.update({county.pk: county for county in state_counties})

    return list(counties.values()) or None

  def _validate_counties_by_code(
    self,
    code: str,
    code_list: Sequence[str],
    counties: Sequence[County],
    *,
    delineation_bulletin: DelineationBulletin | None = None,
  ) -> None:
    found_code = {county.code for county in counties}
    missing_code = sorted(set(code_list) - found_code)
    if missing_code:
      context = (
        f" (delineation {delineation_bulletin.value})"
        if delineation_bulletin is not None
        else ""
      )
      raise CommandError(
        f"Missing counties for {code}{context}: {', '.join(missing_code)}"
      )

  def _validate_counties_by_name(
    self,
    code: str,
    names: Sequence[str],
    counties: Sequence[County],
  ) -> None:
    found_names = {str(county) for county in counties}
    missing_names = sorted(set(names) - found_names)
    if missing_names:
      raise CommandError(f"Missing counties for {code}: {', '.join(missing_names)}")
