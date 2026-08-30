"""Integration controls across bookings, payments, offers and Gold (AC05-AC07)."""

from pathlib import Path
import sys

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_data import generate_data
from src.pipeline import run_pipeline


ALLOWED_QUARANTINE_REASONS = {
    "MISSING_REQUIRED",
    "INVALID_STATUS",
    "INVALID_DATE_ORDER",
    "NEGATIVE_AMOUNT",
    "UNSUPPORTED_CURRENCY",
    "UNKNOWN_OFFER",
    "MISSING_PAYMENT",
    "AMOUNT_MISMATCH",
}


def _run_fixed_case(tmp_path: Path, rows: int = 180) -> tuple[Path, dict]:
    project_root = tmp_path / "fixed-case"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=rows,
        seed=2026,
    )
    result = run_pipeline(
        project_root=project_root,
        batch_id="BATCH_INTEGRATION",
        dedup_mode="latest",
    )
    return project_root, result


def test_silver_has_unique_bookings_and_no_unknown_active_offer(tmp_path: Path) -> None:
    project_root, _ = _run_fixed_case(tmp_path)

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        duplicate_count = db.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT booking_id
                FROM silver_bookings
                GROUP BY booking_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        unknown_or_inactive_offer_count = db.execute(
            """
            SELECT COUNT(*)
            FROM silver_bookings b
            LEFT JOIN bronze_offers o USING (offer_id)
            WHERE o.offer_id IS NULL OR NOT o.active
            """
        ).fetchone()[0]

    assert duplicate_count == 0
    assert unknown_or_inactive_offer_count == 0


def test_rejected_rows_are_traceable_with_an_explicit_reason(tmp_path: Path) -> None:
    project_root, _ = _run_fixed_case(tmp_path)

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        reasons = {
            row[0]
            for row in db.execute(
                "SELECT DISTINCT reason_code FROM quarantine_records"
            ).fetchall()
        }
        incomplete_rows = db.execute(
            """
            SELECT COUNT(*)
            FROM quarantine_records
            WHERE reason_code IS NULL OR TRIM(reason_code) = ''
               OR record_id IS NULL OR TRIM(record_id) = ''
            """
        ).fetchone()[0]

    assert reasons, "The negative dataset should produce auditable quarantine evidence."
    assert reasons <= ALLOWED_QUARANTINE_REASONS
    assert incomplete_rows == 0


def test_gold_matches_an_independent_revenue_oracle(tmp_path: Path) -> None:
    project_root, _ = _run_fixed_case(tmp_path)

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        differences = db.execute(
            """
            WITH eligible AS (
                SELECT
                    CAST(b.service_date AS DATE) AS business_date,
                    b.destination,
                    b.booking_id,
                    b.gross_amount,
                    b.commission_rate
                FROM silver_bookings b
                JOIN silver_payments p USING (booking_id)
                WHERE b.booking_status = 'CONFIRMED'
                  AND p.payment_status = 'PAID'
                  AND ABS(b.gross_amount - p.amount) <= 0.01
                  AND b.currency = 'EUR'
                  AND p.currency = 'EUR'
            ), oracle AS (
                SELECT
                    business_date,
                    destination,
                    COUNT(DISTINCT booking_id) AS confirmed_bookings,
                    ROUND(SUM(gross_amount), 2) AS gross_revenue_eur,
                    ROUND(SUM(gross_amount * commission_rate), 2)
                        AS commission_revenue_eur,
                    ROUND(SUM(gross_amount)
                          - SUM(gross_amount * commission_rate), 2)
                        AS net_revenue_eur
                FROM eligible
                GROUP BY business_date, destination
            )
            SELECT
                COALESCE(o.business_date, g.business_date) AS business_date,
                COALESCE(o.destination, g.destination) AS destination,
                o.confirmed_bookings AS expected_count,
                g.confirmed_bookings AS actual_count,
                o.gross_revenue_eur AS expected_gross,
                g.gross_revenue_eur AS actual_gross,
                o.net_revenue_eur AS expected_net,
                g.net_revenue_eur AS actual_net
            FROM oracle o
            FULL OUTER JOIN gold_daily_revenue g
              USING (business_date, destination)
            WHERE o.business_date IS NULL
               OR g.business_date IS NULL
               OR o.confirmed_bookings <> g.confirmed_bookings
               OR ABS(o.gross_revenue_eur - g.gross_revenue_eur) > 0.01
               OR ABS(o.commission_revenue_eur - g.commission_revenue_eur) > 0.01
               OR ABS(o.net_revenue_eur - g.net_revenue_eur) > 0.01
            """
        ).fetchall()
        gold_columns = {
            row[1] for row in db.execute("PRAGMA table_info('gold_daily_revenue')").fetchall()
        }

    assert differences == []
    assert "client_id" not in gold_columns
