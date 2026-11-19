"""Static region definitions used to exercise sync_static_regions.

Region 901 depends on region 900 (it lists 900 as a component), which forces the
command's dependency-ordering retry loop. CSA sorts before MSA, so 901 is seen
first and must wait for 900 to be created.
"""

REGIONS = [
  {
    "code": "901",
    "name": "Combined Alpha",
    "postal_code": "TX",
    "category": "CSA",
    "components": [
      ("900", "Metro Alpha"),
      ("35001", "Bernalillo"),
    ],
  },
  {
    "code": "900",
    "name": "Metro Alpha",
    "postal_code": "TX",
    "category": "MSA",
    "components": [
      ("48001", "Anderson"),
      ("48003", "Andrews"),
    ],
  },
]
