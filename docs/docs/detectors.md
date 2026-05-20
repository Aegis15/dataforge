# Detectors

Detectors are pure pandas-based scanners that emit typed `Issue` records. Each
issue includes row, column, issue type, severity, confidence, reason, and an
optional expected value.

## Shipped detector families

| Detector | Finds | Typical repair |
| --- | --- | --- |
| `type_mismatch` | Values that do not match the dominant column type | Normalize sentinel or malformed values |
| `decimal_shift` | Numeric values that appear off by powers of ten | Scale to the inferred local magnitude |
| `fd_violation` | Functional dependency conflicts from schema metadata | Align dependent values when a safe majority exists |

## Contract

Detectors do not mutate data. Repairers consume detector output and may propose
fixes, but the write path remains gated by safety, SMT verification, and the
transaction journal.
