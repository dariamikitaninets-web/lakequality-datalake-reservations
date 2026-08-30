# Acceptance criteria

| ID | Criterion | Priority | Expected evidence |
|---|---|---:|---|
| AC01 | Every source file is copied to Bronze with batch ID, filename, and checksum. No file disappears silently. | Critical | Batch manifest and automated check |
| AC02 | A missing mandatory column or invalid type causes a controlled failure or quarantine with a reason code. | Critical | Negative test and Quarantine content |
| AC03 | Reconciliation is exact: raw = accepted + superseded + quarantined; delta = 0. | Critical | SQL query and quality report |
| AC04 | Silver contains one current row per booking ID and retains the greatest `updated_at`. | High | Uniqueness SQL and deduplication test |
| AC05 | No orphan booking-payment or booking-offer relationship reaches Gold. | High | Anti-join SQL and integration test |
| AC06 | Revenue is recognized only for CONFIRMED + PAID. CANCELLED, REFUNDED, and DECLINED contribute zero. | Critical | Independent SQL oracle |
| AC07 | Booking and payment amounts match within EUR 0.01, and statuses belong to the allowed catalogues. | High | Parameterized checks |
| AC08 | `service_date` is on or after `booking_ts`. | Medium | Temporal-validity check |
| AC09 | Reprocessing the same batch is idempotent: Gold count, sum, and hash do not change. | High | Double execution and comparison |
| AC10 | The Gold aggregate matches an independent control calculation from valid source data. | Critical | Source-to-target reconciliation |
| AC11 | The quality report contains volumes, quarantine causes, duplicates, delta, success rate, and duration. | High | JSON/HTML report |
| AC12 | CI/CD blocks the quality gate when a critical check fails and publishes test reports. | Critical | Red and green pipeline evidence |
| AC13 | Laboratory baseline: 100,000 rows process in under 30 seconds with no error and zero reconciliation delta. | Medium | Timestamped measurement; explicitly fictional threshold |
| AC14 | Optional extension: the Kubernetes Job reaches `Completed` with exit code 0. | Optional | `kubectl` evidence only if actually executed |

AC13 is a laboratory assumption, not a client SLA.
