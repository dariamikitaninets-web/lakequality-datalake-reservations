# Risk analysis and test coverage

| ID | Risk | Impact | Likelihood | Priority | Primary control |
|---|---|---:|---:|---:|---|
| R01 | Silent row loss during a join | 5 | 3 | Critical | Raw/Silver/Quarantine reconciliation |
| R02 | An older version replaces the most recent update | 4 | 4 | High | Latest-wins test on `updated_at` |
| R03 | Booking and payment data are inconsistent | 5 | 3 | Critical | Cross-system rules and amount comparison |
| R04 | Schema drift or incompatible type | 4 | 3 | High | Contract and negative tests |
| R05 | Incorrect revenue calculation | 5 | 3 | Critical | SQL oracle independent from implementation |
| R06 | Reprocessing creates duplicates | 4 | 3 | High | Idempotency test |
| R07 | Orphan offer or booking key | 4 | 2 | High | Anti-join and quarantine |
| R08 | Processing time degrades with volume | 3 | 3 | Medium | 10k/100k/500k baseline |
| R09 | Personal identifiers are retained in Gold | 5 | 2 | High | Absence check for raw `client_id` |

## Controlled implementation defect

One code defect is introduced intentionally: deduplication retains the oldest booking version instead of the newest.

Evidence cycle:

1. failing pytest check;
2. blocked CI quality gate;
3. BUG-001 with SQL evidence;
4. correction on a branch;
5. retest and regression;
6. successful pipeline;
7. updated quality assessment.

Invalid rows intentionally placed in the synthetic source data are negative test data, not application defects.
