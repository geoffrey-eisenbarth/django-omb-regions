USA_FIPS = "00000"


def is_state_code(code: str) -> bool:
  """True for a 5-digit state aggregate region code (e.g. '48000'); not USA."""
  return code != USA_FIPS and len(code) == 5 and code.endswith("000")
