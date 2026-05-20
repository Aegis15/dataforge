# DataForge SFT v3 Failure Postmortem

- Failure samples analyzed: `25`
- Dataset counts: `beers`=8, `flights`=8, `hospital`=9
- Failure taxonomy: `missed_repair`=157, `overrepair`=36, `schema_case_error`=26, `wrong_value`=26

## Findings

- Schema/case mistakes such as Index, Id, and Abv remain frequent.
- Wrong-cell index/address/provider repairs show weak row-id discipline.
- Beer samples overrepair style or preserve percent/unit text instead of normalizing.
- Flights samples invent, copy, or date-prefix times instead of abstaining.

## Top Predicted Columns

- `act_arr_time`: 29
- `Index`: 19
- `style`: 14
- `abv`: 5
- `ProviderNumber`: 4
- `Address1`: 4
- `Address2`: 4
- `Abv`: 4
- `Id`: 3
- `beer-name`: 3
