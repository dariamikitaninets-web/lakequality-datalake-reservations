# Data contract v1.1 — simulation assumption

This contract was invented for the exercise and does not represent any real client schema.

## `bookings.csv`

| Field | Logical type | Required | Rule |
|---|---|---:|---|
| `booking_id` | string | yes | `BKG-XXXXXX`; several Bronze versions allowed |
| `offer_id` | string | yes | Must identify an active offer |
| `client_id` | string | yes | Raw only in Bronze; pseudonymized in Silver; absent from Gold |
| `source_channel` | enum | yes | `WEB`, `AGENCY`, or `B2B_API` |
| `booking_ts` | UTC timestamp | yes | Booking creation time |
| `service_date` | date | yes | On or after `booking_ts` date |
| `booking_status` | enum | yes | `PENDING`, `CONFIRMED`, or `CANCELLED` |
| `gross_amount` | decimal(12,2) | yes | Value >= 0 |
| `currency` | string | yes | `EUR` in v1.1 scope |
| `updated_at` | UTC timestamp | yes | The latest version becomes current |

## `payments.jsonl`

| Field | Logical type | Required | Rule |
|---|---|---:|---|
| `payment_id` | string | yes | Unique |
| `booking_id` | string | yes | Must identify a booking |
| `payment_status` | enum | yes | `PAID`, `DECLINED`, or `REFUNDED` |
| `amount` | decimal(12,2) | yes | Value >= 0 and matches booking within EUR 0.01 |
| `currency` | string | yes | `EUR` in v1.1 scope |
| `paid_at` | UTC timestamp | conditional | Required for `PAID` and `REFUNDED` |

## `offers.csv`

| Field | Logical type | Required | Rule |
|---|---|---:|---|
| `offer_id` | string | yes | Unique |
| `destination` | string | yes | Non-empty |
| `commission_rate` | decimal(5,4) | yes | Between 0 and 1 |
| `active` | boolean | yes | Only active offers reach Gold |

## Gold rules

A booking contributes to revenue when its current version is `CONFIRMED`, its payment is `PAID`, amounts match, and the offer is active.

| Measure | Calculation |
|---|---|
| `gross_revenue_eur` | Sum of eligible `gross_amount` |
| `commission_revenue_eur` | Sum of `gross_amount * commission_rate` |
| `net_revenue_eur` | Gross revenue minus commission revenue |
| `confirmed_bookings` | Distinct count of eligible booking IDs |

## Quarantine reason codes

`MISSING_REQUIRED`, `INVALID_STATUS`, `INVALID_DATE_ORDER`, `NEGATIVE_AMOUNT`, `UNSUPPORTED_CURRENCY`, `UNKNOWN_OFFER`, `MISSING_PAYMENT`, and `AMOUNT_MISMATCH`.

No input row may disappear without being classified as current, superseded, or quarantined.
