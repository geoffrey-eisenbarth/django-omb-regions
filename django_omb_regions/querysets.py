from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from .enums import DelineationBulletin

if TYPE_CHECKING:
  from .models import Region  # noqa: F401


class RegionQuerySet[R = "Region"](QuerySet["Region", R]):
  """Region queryset with explicit delineation-aware filters.

  ``current`` keeps rows on the active OMB delineation bulletin; ``static``
  keeps rows that carry no bulletin (the custom categories OMB does not
  delineate, stored as ``NA``), as opposed to the metro categories
  (CSA/MSA/MDIV/MIC) versioned per bulletin; ``current_or_static`` unions
  both. Each accepts extra ``filter`` kwargs so call sites stay terse.
  """

  def current(self, **kwargs: Any) -> RegionQuerySet[R]:
    return self.filter(delineation_bulletin=DelineationBulletin.get_current(), **kwargs)

  def static(self, **kwargs: Any) -> RegionQuerySet[R]:
    return self.filter(delineation_bulletin=DelineationBulletin.NA, **kwargs)

  def current_or_static(self, **kwargs: Any) -> RegionQuerySet[R]:
    bulletins = [DelineationBulletin.get_current(), DelineationBulletin.NA]
    return self.filter(delineation_bulletin__in=bulletins, **kwargs)
