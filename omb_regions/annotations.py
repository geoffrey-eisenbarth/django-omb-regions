from typing import TYPE_CHECKING

from django.db.models import (
  Case,
  CharField,
  Count,
  F,
  OuterRef,
  Subquery,
  Value,
  When,
)
from django.db.models.functions import Coalesce, Concat, Substr

from .constants import USA_FIPS
from .enums import DelineationBulletin
from .models import County, Region, State

if TYPE_CHECKING:
  from django.db.models import Expression


def geography_field_lookup(
  from_field: str,
  to_field: str,
  delineation_bulletin: DelineationBulletin | OuterRef | None = None,
) -> Expression:
  delineation_bulletin = delineation_bulletin or DelineationBulletin.get_current()
  if to_field == "name":
    usa_name = Value("United States")
  else:
    raise NotImplementedError

  return Case(
    When(**{from_field: USA_FIPS}, then=usa_name),
    default=Coalesce(
      Subquery(
        Region.versions.filter(
          code=OuterRef(from_field),
          delineation_bulletin=delineation_bulletin,
        ).values(to_field)[:1]
      ),
      Subquery(
        County.objects.filter(
          code=OuterRef(from_field),
        ).values(to_field)[:1]
      ),
      Subquery(
        State.objects.filter(
          counties__code=OuterRef(from_field),
        ).values(to_field)[:1]
      ),
    ),
    output_field=CharField(),
  )


def geography_category_lookup(
  from_field: str,
  delineation_bulletin: DelineationBulletin | OuterRef | None = None,
) -> Expression:
  delineation_bulletin = delineation_bulletin or DelineationBulletin.get_current()
  return Case(
    When(**{from_field: USA_FIPS}, then=Value("NATION")),
    When(**{f"{from_field}__regex": r"^\d{2}000$"}, then=Value("STATE")),
    default=Coalesce(
      Subquery(
        Region.versions.filter(
          code=OuterRef(from_field),
          delineation_bulletin=delineation_bulletin,
        ).values("category")[:1]
      ),
      Value("COUNTY"),
    ),
    output_field=CharField(),
  )


def geography_parent_lookup(
  target: str,
  source: str | None = None,
  from_field: str = "region",
  to_field: str = "code",
  delineation_bulletin: DelineationBulletin | OuterRef | None = None,
) -> Expression | Subquery:
  """Helper for fetching a parent for a given region code.

  If MSA belongs to multiple states, or e.g., Bowie, TX county belongs to two
  MSAs (Texarkana TX-NM, and Texarkana TX), then this will fetch the last
  parent, since that allows Bowie and "Texarkana TX" to work.

  """
  delineation_bulletin = delineation_bulletin or DelineationBulletin.get_current()
  if source is None:
    source = {
      "USCBD": "STATE",
      "USCBR": "STATE",
      "FROST": "MSA",
    }.get(target, "COUNTY")

  if target == "NATION":
    return Value(USA_FIPS, output_field=CharField())

  if source == "COUNTY":
    if target == "STATE":
      return Concat(
        Substr(F(from_field), 1, 2),
        Value("000"),
        output_field=CharField(),
      )
    else:
      return Subquery(
        Region.versions.filter(
          category=target,
          delineation_bulletin=delineation_bulletin,
          counties__code=OuterRef(from_field),
        ).values(to_field)[:1],  # .reverse()[:1].values(to_field)
        output_field=CharField(),
      )

  elif target == "STATE":
    if not Region.Category.is_covering(source):
      raise ValueError(f"The {source} category does not cover the {target} category.")

    return Subquery(
      Region.versions.filter(
        category=source,
        delineation_bulletin=delineation_bulletin,
        code=OuterRef(from_field),
      ).values("counties__state__code")[:1],
      output_field=CharField(),
    )

  elif (source, target) in {
    (Region.Category.COG, Region.Category.EPR),
    (Region.Category.MSA, Region.Category.FROST),
  }:
    return Subquery(
      Region.versions.filter(
        category=target,
        delineation_bulletin=delineation_bulletin,
        counties__regions__category=source,
        counties__regions__code=OuterRef(from_field),
      ).values("code")[:1],
      output_field=CharField(),
    )

  else:
    raise NotImplementedError


def geography_child_count_lookup(
  target: str,
  source: str | None = None,
  from_field: str = "parent_region",
  delineation_bulletin: DelineationBulletin | OuterRef | None = None,
) -> Subquery:
  """Can't just use `Count()` since it messes with Subquery/OuterRef

  https://docs.djangoproject.com/en/4.2/ref/models/expressions/#using-aggregates-within-a-subquery-expression
  """
  delineation_bulletin = delineation_bulletin or DelineationBulletin.get_current()
  if source is None:
    source = {
      "USCBD": "STATE",
      "USCBR": "STATE",
      "FROST": "MSA",
    }.get(target, "COUNTY")

  if (source == "COUNTY") and (target == "STATE"):
    return Subquery(
      County.objects.filter(
        state__code=OuterRef(from_field),
      )
      .order_by()
      .values(
        "state__code",
      )
      .annotate(
        count=Count("code"),
      )
      .values("count")[:1]
    )

  if source == "COUNTY":
    return Subquery(
      Region.versions.filter(
        category=target,
        delineation_bulletin=delineation_bulletin,
        code=OuterRef(from_field),
      )
      .order_by()
      .annotate(
        count=Count("counties"),
      )
      .values("count")[:1]
    )

  if target == "STATE":
    if not Region.Category.is_covering(source):
      raise ValueError

    return Subquery(
      Region.versions.filter(
        category=source,
        delineation_bulletin=delineation_bulletin,
        counties__state__code=OuterRef(from_field),
      )
      .order_by()
      .values(
        "counties__state__code",
      )
      .annotate(
        count=Count("code", distinct=True),
      )
      .values("count")[:1]
    )

  if (source, target) in {
    (Region.Category.COG, Region.Category.EPR),
    (Region.Category.MSA, Region.Category.FROST),
  }:
    return Subquery(
      Region.versions.filter(
        category=source,
        delineation_bulletin=delineation_bulletin,
        counties__regions__category=target,
        counties__regions__code=OuterRef(from_field),
      )
      .order_by()
      .values(
        "counties__regions__code",
      )
      .annotate(
        count=Count("code", distinct=True),
      )
      .values("count")[:1]
    )

  raise NotImplementedError(
    f"Cannot count {source} children for {target} geography regrouping."
  )
