from django.contrib.gis.db import models
from django.contrib.gis.db.models import Union
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.utils.translation import gettext_lazy as _

from .enums import DelineationBulletin, Geography
from .managers import CurrentDelineationManager, MetroManager

WGS_SRID = 4326  # World Geodetic System 1984
AREA_SRID = 2163  # US National Atlas Equal Area
SQ_M_TO_SQ_MI = 3.86102159e-7


class State(models.Model):
  fips2 = models.CharField(
    max_length=2,
    unique=True,
    verbose_name=_("FIPS State Code"),
  )
  code = models.CharField(
    max_length=5,
    unique=True,
    verbose_name=_("Region Code"),
  )
  name = models.CharField(
    max_length=255,
    unique=True,
    verbose_name=_("Name"),
  )
  postal_code = models.CharField(
    max_length=2,
    unique=True,
    verbose_name=_("Postal Code"),
  )
  shape = models.MultiPolygonField(
    srid=WGS_SRID,
    spatial_index=True,
    verbose_name=_("Border"),
  )
  sq_miles = models.FloatField(
    verbose_name=_("Square Miles"),
  )

  class Meta:
    ordering = ["code"]
    verbose_name = _("State")
    verbose_name_plural = _("States")

  def __str__(self) -> str:
    return f"[FIPS {self.fips2}] {self.name}"

  def set_sq_miles(self, save: bool = False) -> None:
    projected = self.shape.transform(AREA_SRID, clone=True)
    self.sq_miles = projected.area * SQ_M_TO_SQ_MI
    if save:
      self.save()


class County(models.Model):
  code = models.CharField(
    max_length=5,
    unique=True,
    verbose_name=_("Region Code"),
  )
  fips2 = models.CharField(
    max_length=2,
    verbose_name=_("FIPS State Code"),
  )
  fips3 = models.CharField(
    max_length=3,
    verbose_name=_("FIPS County Code"),
  )
  name = models.CharField(
    max_length=255,
    verbose_name=_("Name"),
  )
  postal_code = models.CharField(
    max_length=2,
    verbose_name=_("Postal Code"),
  )
  shape = models.MultiPolygonField(
    srid=WGS_SRID,
    spatial_index=True,
    verbose_name=_("Border"),
  )
  sq_miles = models.FloatField(
    verbose_name=_("Square Miles"),
  )
  state = models.ForeignKey(
    State,
    on_delete=models.CASCADE,
    related_name="counties",
    verbose_name=_("State"),
  )

  class Meta:
    ordering = ["code"]
    verbose_name = _("County")
    verbose_name_plural = _("Counties")

    constraints = [
      models.UniqueConstraint(
        name="unique_fips_code",
        fields=["fips2", "fips3"],
      ),
    ]

  def __str__(self) -> str:
    return f"[FIPS {self.code}] {self.name}"

  def set_sq_miles(self, save: bool = False) -> None:
    projected = self.shape.transform(AREA_SRID, clone=True)
    self.sq_miles = projected.area * SQ_M_TO_SQ_MI
    if save:
      self.save()


class Region(models.Model):
  #: Backwards-compatible alias; the enum now lives in geography.enums.
  Category = Geography

  category = models.CharField(
    max_length=20,
    choices=Geography.regions,
    verbose_name=_("Category"),
  )
  name = models.CharField(
    max_length=255,
    verbose_name=_("Name"),
  )
  code = models.CharField(
    max_length=10,
    verbose_name=_("Reference Code"),
  )
  postal_code = models.CharField(
    max_length=20,
    verbose_name=_("Postal Code"),
  )
  delineation_bulletin = models.CharField(
    max_length=5,
    choices=DelineationBulletin.choices,
    db_index=True,
    verbose_name=_("Delineation Bulletin"),
  )
  counties = models.ManyToManyField(
    County,
    related_name="regions",
    verbose_name=_("Counties"),
  )
  shape = models.MultiPolygonField(
    srid=WGS_SRID,
    spatial_index=True,
    verbose_name=_("Border"),
  )
  sq_miles = models.FloatField(
    verbose_name=_("Square Miles"),
  )

  versions = models.Manager()
  current = CurrentDelineationManager()
  metros = MetroManager()

  class Meta:
    ordering = ["category", "code", "-delineation_bulletin"]
    verbose_name = _("Region")
    verbose_name_plural = _("Regions")

    constraints = [
      models.UniqueConstraint(
        name="unique_region",
        fields=["code", "delineation_bulletin"],
      ),
    ]

  def __str__(self) -> str:
    return f"[{self.category} {self.code}] {self.name}"

  def set_sq_miles(self, save: bool = False) -> None:
    if self.shape is None:
      raise ValueError(_("Cannot calculate sq_miles without a shape."))
    projected = self.shape.transform(AREA_SRID, clone=True)
    self.sq_miles = projected.area * SQ_M_TO_SQ_MI
    if save:
      self.save()

  def set_shape(
    self,
    counties: models.QuerySet[County] | None = None,
    save: bool = False,
  ) -> None:
    if counties is None:
      counties = self.counties.all()

    shape = counties.aggregate(shape=Union("shape"))["shape"]
    if shape is None:
      raise ValueError(_("Cannot set a shape without counties."))
    if isinstance(shape, Polygon):
      shape = MultiPolygon(shape, srid=shape.srid)
    elif not isinstance(shape, MultiPolygon):
      raise ValueError(
        _(f"Expected Polygon or MultiPolygon shape, got {shape.geom_type}.")
      )

    self.shape = shape
    if save:
      self.save()

  @property
  def is_metro(self) -> bool:
    return self.category in {
      self.Category.MSA,
      self.Category.MDIV,
      self.Category.MIC,
      self.Category.FROST,
    }
