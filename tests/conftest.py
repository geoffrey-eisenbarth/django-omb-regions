from io import StringIO

import pytest
from django.core.management import call_command

from django_omb_regions import enums
from tests.geo import make_state


@pytest.fixture(autouse=True)
def reset_extra_categories():
  """Isolate the module-global downstream category registry between tests."""
  original = dict(enums._EXTRA_CATEGORIES)
  yield
  enums._EXTRA_CATEGORIES.clear()
  enums._EXTRA_CATEGORIES.update(original)


@pytest.fixture
def grid(db):
  """Two adjacent-plus-distant states of 1-degree square counties.

  Layout over Texas-ish coordinates (lower-left corners), so the US equal-area
  projection used for sq_miles behaves realistically:
    48001 (-100,31) 48003 (-99,31) 35001 (-98,31)  -- a contiguous strip
    35003 (-95,34)                                  -- far, for MultiPolygon unions
  """
  tx = make_state(
    "48",
    "Texas",
    "TX",
    [
      ("001", "Anderson", -100.0, 31.0),
      ("003", "Andrews", -99.0, 31.0),
    ],
  )
  nm = make_state(
    "35",
    "New Mexico",
    "NM",
    [
      ("001", "Bernalillo", -98.0, 31.0),
      ("003", "Catron", -95.0, 34.0),
    ],
  )
  return {"tx": tx, "nm": nm}


def run_sync(**options) -> str:
  """Run sync_static_regions and return captured stdout."""
  out = StringIO()
  call_command("sync_static_regions", stdout=out, **options)
  return out.getvalue()
