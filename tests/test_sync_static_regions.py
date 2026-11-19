import sys
import types

import pytest
from django.core.management.base import CommandError
from django.test import override_settings

from django_omb_regions.enums import DelineationBulletin
from django_omb_regions.models import Region
from tests.conftest import run_sync

pytestmark = pytest.mark.django_db

CURRENT = DelineationBulletin.get_current()


def _install_defs(monkeypatch, name, regions):
  module = types.ModuleType(name)
  module.REGIONS = regions
  monkeypatch.setitem(sys.modules, name, module)
  return name


def _region_def(code, category, components, **extra):
  return {
    "code": code,
    "name": f"Region {code}",
    "postal_code": "TX",
    "category": category,
    "components": components,
    **extra,
  }


def test_end_to_end_builds_regions_with_membership_and_shape(grid):
  out = run_sync(defs="tests.fixture_defs", bulletin="B2301")

  assert "2 created" in out

  metro = Region.objects.get(code="900")
  assert metro.category == Region.Category.MSA
  assert metro.delineation_bulletin == "B2301"
  assert set(metro.counties.values_list("code", flat=True)) == {"48001", "48003"}
  assert metro.shape.num_geom == 1
  assert metro.sq_miles > 0

  # 901 depends on 900 (dependency-ordering retry loop); it inherits 900's
  # counties plus its own, spanning both states.
  combined = Region.objects.get(code="901")
  assert set(combined.counties.values_list("code", flat=True)) == {
    "48001",
    "48003",
    "35001",
  }


def test_missing_only_is_idempotent(grid):
  run_sync(defs="tests.fixture_defs", bulletin="B2301")
  out = run_sync(defs="tests.fixture_defs", bulletin="B2301", missing_only=True)

  assert "2 skipped" in out
  assert Region.objects.count() == 2


def test_rerun_updates_and_prunes_stale_counties(grid, monkeypatch):
  run_sync(defs="tests.fixture_defs", bulletin="B2301")
  original = Region.objects.get(code="900").sq_miles

  shrunk = _install_defs(
    monkeypatch,
    "shrunk_defs",
    [_region_def("900", "MSA", [("48001", "Anderson")])],
  )
  out = run_sync(defs=shrunk, bulletin="B2301")

  metro = Region.objects.get(code="900")
  assert "1 updated" in out
  assert set(metro.counties.values_list("code", flat=True)) == {"48001"}
  assert metro.sq_miles < original


def test_category_filter_syncs_only_matching_defs(grid):
  run_sync(defs="tests.fixture_defs", bulletin="B2301", category="MSA")

  assert Region.objects.filter(code="900").exists()
  assert not Region.objects.filter(code="901").exists()


def test_per_def_bulletin_overrides_default(grid, monkeypatch):
  name = _install_defs(
    monkeypatch,
    "override_defs",
    [_region_def("900", "MSA", [("48001", "A")], delineation_bulletin="B2001")],
  )
  run_sync(defs=name, bulletin="B2301")

  assert Region.objects.get(code="900").delineation_bulletin == "B2001"


def test_partial_resolution_raises_and_rolls_back(grid, monkeypatch):
  # 902's second component county does not exist, so the whole run must abort
  # and leave no regions behind (transaction rollback).
  name = _install_defs(
    monkeypatch,
    "partial_defs",
    [
      _region_def("900", "MSA", [("48001", "A"), ("48003", "B")]),
      _region_def("902", "MSA", [("48001", "A"), ("48999", "Missing")]),
    ],
  )
  with pytest.raises(CommandError):
    run_sync(defs=name, bulletin="B2301")

  assert Region.objects.count() == 0


def test_defs_arg_beats_setting(grid, monkeypatch):
  good = _install_defs(
    monkeypatch,
    "good_defs",
    [_region_def("900", "MSA", [("48001", "A")])],
  )
  _install_defs(monkeypatch, "empty_defs", [])

  with override_settings(DJANGO_OMB_REGIONS_STATIC_DEFS="empty_defs"):
    run_sync(defs=good, bulletin="B2301")

  assert Region.objects.filter(code="900").exists()


def test_setting_used_when_no_arg(grid, monkeypatch):
  name = _install_defs(
    monkeypatch,
    "setting_defs",
    [_region_def("900", "MSA", [("48001", "A")])],
  )
  with override_settings(DJANGO_OMB_REGIONS_STATIC_DEFS=name):
    run_sync(bulletin="B2301")

  assert Region.objects.filter(code="900").exists()


def test_bad_defs_path_raises(grid):
  with pytest.raises(CommandError):
    run_sync(defs="django_omb_regions.does_not_exist", bulletin="B2301")


def test_defs_module_without_regions_raises(grid, monkeypatch):
  module = types.ModuleType("no_regions_defs")
  monkeypatch.setitem(sys.modules, "no_regions_defs", module)
  with pytest.raises(CommandError):
    run_sync(defs="no_regions_defs", bulletin="B2301")
