from typing import TYPE_CHECKING

from django.db.models import QuerySet

from .enums import DelineationBulletin

if TYPE_CHECKING:
  from .models import Region  # noqa: F401


class CurrentDelineationQuerySet[R = "Region"](QuerySet["Region", R]):
  def current_delineation(self) -> CurrentDelineationQuerySet[R]:
    return self.filter(delineation_bulletin=DelineationBulletin.get_current())
