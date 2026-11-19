# TODO

## Derive state portions of multistate MSAs (pending)

Add new delineated category for the state portions of MIC, MDIV, MSA, CSA that cross state lines.
Derive each portion from the parent MIC/MDIV/MSA/CSA's county membership for the same OMB bulletin, grouped by county state.
Use the categories MIC_SP, MDIV_SP, MSA_SP, CSA_SP as the categories ("SP" stands for "State Portion").

Use stable identifiers based on parent MIC/MDIV/MSA/CSA code and state FIPS that cannot collide with county or
metro codes, perhaps something involving State.fips2 or postal_code; run your ideas by me before implementing them.
Preserve a way to resolve the parent MSA and state. These would be library-derived regions, not new official OMB geographies.

Keep the full MSA and its portions independently queryable. Within a bulletin,
the portions should partition the parent's county membership; membership can
change between bulletins.

If you have any questions or are less than 90% on anything, ask me followup questions.
