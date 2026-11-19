from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import County, Region, State

if TYPE_CHECKING:
  from typing import Any

  from django.db.models import QuerySet
  from django.db.models.fields.related import ManyToManyField
  from django.forms.models import ModelMultipleChoiceField
  from django.http import HttpRequest


@admin.register(State)
class StateAdmin(GISModelAdmin[State]):
  search_fields = list_display = (
    "name",
    "postal_code",
    "code",
  )


@admin.register(County)
class CountyAdmin(GISModelAdmin[County]):
  search_fields = list_display = (
    "name",
    "postal_code",
    "code",
  )

  def get_queryset(
    self,
    request: HttpRequest,
  ) -> QuerySet[County, County]:
    return super().get_queryset(request).select_related("state").defer("shape")


@admin.register(Region)
class RegionAdmin(GISModelAdmin[Region]):
  search_fields = list_display = (
    "name",
    "category",
    "code",
    "delineation_bulletin",
  )
  list_filter = (
    "category",
    "delineation_bulletin",
  )
  autocomplete_fields = ("counties",)

  def formfield_for_manytomany(
    self,
    db_field: ManyToManyField[County, Any],
    request: HttpRequest,
    **kwargs: Any,
  ) -> ModelMultipleChoiceField[County] | None:
    if db_field.name == "counties":
      kwargs["queryset"] = (
        County.objects.select_related("state")
        .defer("shape")
        .order_by("postal_code", "name")
      )
    return super().formfield_for_manytomany(db_field, request, **kwargs)
