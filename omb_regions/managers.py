from typing import TYPE_CHECKING

from django.db import models

from .querysets import CurrentDelineationQuerySet

if TYPE_CHECKING:
  from .models import Region


class CurrentDelineationManager(models.Manager["Region"]):
  def get_queryset(self) -> CurrentDelineationQuerySet[Region]:
    queryset = CurrentDelineationQuerySet(
      model=self.model,
      using=self._db,
    )
    return queryset.current_delineation()


class MetroManager(CurrentDelineationManager):
  def get_queryset(self) -> CurrentDelineationQuerySet[Region]:
    return (
      super()
      .get_queryset()
      .filter(
        category__in=[
          self.model.Category.MIC,
          self.model.Category.MDIV,
          self.model.Category.MSA,
        ]
      )
    )
