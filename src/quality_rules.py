"""Shared data contracts and quality checks for the LakeQuality pipeline.

The rules live in a separate module so that a tester can read the expected
behaviour without first understanding the pipeline implementation.  SQL is
used for the checks on purpose: it makes every assertion easy to reproduce in
DuckDB or DBeaver.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


BOOKING_REQUIRED_COLUMNS: tuple[str, ...] = (
    "booking_id",
    "offer_id",
    "client_id",
    "source_channel",
    "booking_status",
    "booking_ts",
    "service_date",
    "gross_amount",
    "currency",
    "updated_at",
)

PAYMENT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "payment_id",
    "booking_id",
    "payment_status",
    "amount",
    "currency",
    "paid_at",
)

OFFER_REQUIRED_COLUMNS: tuple[str, ...] = (
    "offer_id",
    "destination",
    "commission_rate",
    "active",
)

BOOKING_ALLOWED_STATUSES: tuple[str, ...] = (
    "PENDING",
    "CONFIRMED",
    "CANCELLED",
)

PAYMENT_ALLOWED_STATUSES: tuple[str, ...] = (
    "PAID",
    "DECLINED",
    "REFUNDED",
)


class DataContractError(ValueError):
    """Raised when an input file is missing a mandatory column."""


def validate_columns(
    actual_columns: Iterable[str],
    required_columns: Sequence[str],
    source_name: str,
) -> None:
    """Validate a source schema before transformation starts.

    Row-level nulls are quarantined later.  A completely missing column is a
    contract failure because the row cannot be interpreted safely.
    """

    actual = {column.strip() for column in actual_columns}
    missing = [column for column in required_columns if column not in actual]
    if missing:
        missing_text = ", ".join(missing)
        raise DataContractError(
            f"{source_name}: missing mandatory column(s): {missing_text}"
        )


def sql_list(values: Sequence[str]) -> str:
    """Return a safely quoted SQL list for constants controlled by this code."""

    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def booking_validation_case(alias: str = "b") -> str:
    """SQL CASE returning the first booking quarantine reason, or NULL."""

    required = (
        "booking_id",
        "offer_id",
        "client_id",
        "source_channel",
        "booking_status",
        "booking_ts",
        "service_date",
        "gross_amount",
        "currency",
        "updated_at",
    )
    missing_predicate = " OR ".join(
        f"NULLIF(TRIM({alias}.{column}), '') IS NULL" for column in required
    )
    statuses = sql_list(BOOKING_ALLOWED_STATUSES)

    return f"""
        CASE
            WHEN {missing_predicate}
                THEN 'MISSING_REQUIRED'
            WHEN TRY_CAST({alias}.gross_amount AS DECIMAL(18, 2)) IS NULL
                THEN 'MISSING_REQUIRED'
            WHEN TRY_CAST({alias}.gross_amount AS DECIMAL(18, 2)) < 0
                THEN 'NEGATIVE_AMOUNT'
            WHEN TRY_CAST({alias}.booking_ts AS TIMESTAMP) IS NULL
                 OR TRY_CAST({alias}.service_date AS DATE) IS NULL
                 OR TRY_CAST({alias}.updated_at AS TIMESTAMP) IS NULL
                THEN 'MISSING_REQUIRED'
            WHEN TRY_CAST({alias}.service_date AS DATE)
                 < CAST(TRY_CAST({alias}.booking_ts AS TIMESTAMP) AS DATE)
                THEN 'INVALID_DATE_ORDER'
            WHEN UPPER(TRIM({alias}.booking_status)) NOT IN ({statuses})
                THEN 'INVALID_STATUS'
            WHEN UPPER(TRIM({alias}.source_channel)) NOT IN ('WEB', 'AGENCY', 'B2B_API')
                THEN 'INVALID_STATUS'
            WHEN UPPER(TRIM({alias}.currency)) <> 'EUR'
                THEN 'UNSUPPORTED_CURRENCY'
            WHEN o.offer_id IS NULL
                THEN 'UNKNOWN_OFFER'
            WHEN NOT o.active
                THEN 'UNKNOWN_OFFER'
            ELSE NULL
        END
    """.strip()


def payment_validation_case(alias: str = "p") -> str:
    """SQL CASE returning the first payment quarantine reason, or NULL.

    The expression expects aliases ``b`` (a valid booking) and ``p`` (payment)
    in its query context.
    """

    required = (
        "payment_id",
        "booking_id",
        "payment_status",
        "amount",
        "currency",
        "paid_at",
    )
    missing_predicate = " OR ".join(
        f"NULLIF(TRIM({alias}.{column}), '') IS NULL" for column in required
    )
    statuses = sql_list(PAYMENT_ALLOWED_STATUSES)

    return f"""
        CASE
            WHEN {missing_predicate}
                THEN 'MISSING_REQUIRED'
            WHEN TRY_CAST({alias}.amount AS DECIMAL(18, 2)) IS NULL
                THEN 'MISSING_REQUIRED'
            WHEN TRY_CAST({alias}.amount AS DECIMAL(18, 2)) < 0
                THEN 'NEGATIVE_AMOUNT'
            WHEN UPPER(TRIM({alias}.payment_status)) IN ('PAID', 'REFUNDED')
                 AND TRY_CAST({alias}.paid_at AS TIMESTAMP) IS NULL
                THEN 'MISSING_REQUIRED'
            WHEN UPPER(TRIM({alias}.payment_status)) NOT IN ({statuses})
                THEN 'INVALID_STATUS'
            WHEN UPPER(TRIM({alias}.currency)) <> 'EUR'
                THEN 'UNSUPPORTED_CURRENCY'
            WHEN b.booking_id IS NULL
                THEN 'MISSING_REQUIRED'
            WHEN ABS(
                TRY_CAST({alias}.amount AS DECIMAL(18, 2)) - b.gross_amount
            ) > 0.01
                THEN 'AMOUNT_MISMATCH'
            ELSE NULL
        END
    """.strip()


def stable_rows_hash(rows: Iterable[Sequence[Any]]) -> str:
    """Hash ordered query results for an idempotence proof."""

    normalized = [
        [None if value is None else str(value) for value in row] for row in rows
    ]
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_check(
    check_id: str,
    name: str,
    passed: bool,
    severity: str,
    actual: Any,
    expected: Any,
    evidence: str,
) -> dict[str, Any]:
    """Create one serialisable quality-check record."""

    return {
        "id": check_id,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "severity": severity,
        "actual": actual,
        "expected": expected,
        "evidence": evidence,
    }


def evaluate_quality(
    connection: Any,
    *,
    manifest_ok: bool,
    reconciliation_difference: int,
) -> list[dict[str, Any]]:
    """Execute the main automated quality gate against DuckDB tables."""

    scalar = lambda sql: connection.execute(sql).fetchone()[0]

    duplicate_current = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM (
                SELECT booking_id
                FROM silver_bookings
                GROUP BY booking_id
                HAVING COUNT(*) > 1
            )
            """
        )
    )
    stale_versions = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM silver_bookings AS s
            JOIN (
                SELECT booking_id,
                       MAX(TRY_CAST(updated_at AS TIMESTAMP)) AS latest_updated_at
                FROM booking_validation
                WHERE validation_reason IS NULL
                GROUP BY booking_id
            ) AS expected USING (booking_id)
            WHERE s.updated_at <> expected.latest_updated_at
            """
        )
    )
    orphan_gold = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM gold_revenue_detail AS g
            LEFT JOIN silver_bookings AS b USING (booking_id)
            LEFT JOIN silver_payments AS p USING (payment_id)
            WHERE b.booking_id IS NULL OR p.payment_id IS NULL
            """
        )
    )
    ineligible_gold = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM gold_revenue_detail
            WHERE booking_status <> 'CONFIRMED'
               OR payment_status <> 'PAID'
            """
        )
    )
    invalid_temporal = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM silver_bookings
            WHERE service_date < CAST(booking_ts AS DATE)
            """
        )
    )
    amount_mismatches = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM silver_payments AS p
            JOIN silver_bookings AS b USING (booking_id)
            WHERE ABS(p.amount - b.gross_amount) > 0.01
            """
        )
    )
    gold_oracle_difference = int(
        scalar(
            """
            WITH expected AS (
                SELECT
                    b.service_date AS business_date,
                    b.destination,
                    ROUND(SUM(b.gross_amount), 2) AS gross_revenue_eur,
                    ROUND(SUM(b.gross_amount * b.commission_rate), 2)
                        AS commission_revenue_eur,
                    ROUND(
                        SUM(b.gross_amount)
                        - SUM(b.gross_amount * b.commission_rate),
                        2
                    ) AS net_revenue_eur,
                    COUNT(DISTINCT b.booking_id) AS confirmed_bookings
                FROM silver_bookings AS b
                JOIN latest_payment_per_booking AS p USING (booking_id)
                WHERE b.booking_status = 'CONFIRMED'
                  AND p.payment_status = 'PAID'
                GROUP BY b.service_date, b.destination
            ), comparison AS (
                (SELECT business_date, destination, gross_revenue_eur,
                        commission_revenue_eur, net_revenue_eur,
                        confirmed_bookings
                 FROM expected
                 EXCEPT ALL
                 SELECT business_date, destination, gross_revenue_eur,
                        commission_revenue_eur, net_revenue_eur,
                        confirmed_bookings
                 FROM gold_daily_revenue)
                UNION ALL
                (SELECT business_date, destination, gross_revenue_eur,
                        commission_revenue_eur, net_revenue_eur,
                        confirmed_bookings
                 FROM gold_daily_revenue
                 EXCEPT ALL
                 SELECT business_date, destination, gross_revenue_eur,
                        commission_revenue_eur, net_revenue_eur,
                        confirmed_bookings
                 FROM expected)
            )
            SELECT COUNT(*) FROM comparison
            """
        )
    )
    gold_personal_columns = int(
        scalar(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_name IN ('gold_daily_revenue', 'gold_revenue_detail')
              AND column_name IN ('client_id', 'email', 'first_name', 'last_name')
            """
        )
    )

    return [
        make_check(
            "AC01",
            "Bronze manifest and immutable copies",
            manifest_ok,
            "CRITICAL",
            manifest_ok,
            True,
            "data/bronze/<batch_id>/manifest.json",
        ),
        make_check(
            "AC03",
            "Booking reconciliation",
            reconciliation_difference == 0,
            "CRITICAL",
            reconciliation_difference,
            0,
            "raw = current + superseded + quarantined",
        ),
        make_check(
            "AC04A",
            "One current row per booking",
            duplicate_current == 0,
            "HIGH",
            duplicate_current,
            0,
            "GROUP BY booking_id HAVING COUNT(*) > 1",
        ),
        make_check(
            "AC04B",
            "Latest booking version retained",
            stale_versions == 0,
            "HIGH",
            stale_versions,
            0,
            "silver.updated_at = MAX(valid bronze.updated_at)",
        ),
        make_check(
            "AC05",
            "No orphan relation reaches Gold",
            orphan_gold == 0,
            "HIGH",
            orphan_gold,
            0,
            "Gold detail anti-join to Silver bookings and payments",
        ),
        make_check(
            "AC06",
            "Revenue only for CONFIRMED and PAID",
            ineligible_gold == 0,
            "CRITICAL",
            ineligible_gold,
            0,
            "Gold detail status control",
        ),
        make_check(
            "AC07",
            "Booking and payment amounts agree within EUR 0.01",
            amount_mismatches == 0,
            "HIGH",
            amount_mismatches,
            0,
            "ABS(payment.amount - booking.gross_amount) <= 0.01",
        ),
        make_check(
            "AC08",
            "Service date is not before booking date",
            invalid_temporal == 0,
            "MEDIUM",
            invalid_temporal,
            0,
            "service_date >= CAST(booking_ts AS DATE)",
        ),
        make_check(
            "AC10",
            "Gold equals independent control aggregation",
            gold_oracle_difference == 0,
            "CRITICAL",
            gold_oracle_difference,
            0,
            "Bidirectional EXCEPT ALL between expected and Gold",
        ),
        make_check(
            "R09",
            "No raw personal identifier in Gold",
            gold_personal_columns == 0,
            "HIGH",
            gold_personal_columns,
            0,
            "Gold schema inspection",
        ),
    ]


def quality_gate_decision(checks: Sequence[Mapping[str, Any]]) -> str:
    """Return GO unless a critical or high check failed."""

    blocking = {"CRITICAL", "HIGH"}
    has_blocker = any(
        check.get("status") == "FAIL" and check.get("severity") in blocking
        for check in checks
    )
    return "NO-GO" if has_blocker else "GO"


def load_previous_report(path: Path) -> dict[str, Any] | None:
    """Load the previous run if present; malformed reports are ignored safely."""

    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
