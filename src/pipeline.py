"""Local Source -> Bronze -> Silver/Quarantine -> Gold pipeline.

Two execution modes are available:

* ``fixed`` keeps the newest booking version (the expected behaviour);
* ``buggy`` deliberately keeps the oldest version for the BUG-001 exercise.

Every input is synthetic.  The implementation is intentionally explicit and
compact enough for a junior QA engineer to explain during an interview.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .quality_rules import (
    BOOKING_REQUIRED_COLUMNS,
    OFFER_REQUIRED_COLUMNS,
    PAYMENT_REQUIRED_COLUMNS,
    DataContractError,
    booking_validation_case,
    evaluate_quality,
    load_previous_report,
    make_check,
    payment_validation_case,
    quality_gate_decision,
    stable_rows_hash,
    validate_columns,
)


DEFAULT_BATCH_ID = "BATCH_DEMO_001"


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_string(value: str | Path) -> str:
    """Quote a local path or value for a DuckDB SQL literal."""

    return "'" + str(value).replace("'", "''") + "'"


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        try:
            return next(reader)
        except StopIteration as error:
            raise DataContractError(f"{path.name}: empty source file") from error


def _read_jsonl_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise DataContractError(
                        f"{path.name}: first JSONL record is not an object"
                    )
                return list(payload)
    raise DataContractError(f"{path.name}: empty source file")


def _copy_to_parquet(connection: Any, query: str, path: Path) -> None:
    """Write one deterministic Parquet file, replacing only that exact output."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection.execute(
        f"COPY ({query}) TO {_sql_string(path)} "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _required_sources(source_dir: Path) -> dict[str, Path]:
    paths = {
        "bookings": source_dir / "bookings.csv",
        "payments": source_dir / "payments.jsonl",
        "offers": source_dir / "offers.csv",
    }
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        names = ", ".join(missing)
        raise FileNotFoundError(
            f"Missing source file(s): {names}. Run "
            "`python -m src.generate_data --rows 1000` first."
        )
    return paths


def _validate_contracts(paths: dict[str, Path]) -> None:
    validate_columns(
        _read_csv_header(paths["bookings"]),
        BOOKING_REQUIRED_COLUMNS,
        paths["bookings"].name,
    )
    validate_columns(
        _read_jsonl_columns(paths["payments"]),
        PAYMENT_REQUIRED_COLUMNS,
        paths["payments"].name,
    )
    validate_columns(
        _read_csv_header(paths["offers"]),
        OFFER_REQUIRED_COLUMNS,
        paths["offers"].name,
    )


def _prepare_bronze(
    connection: Any,
    *,
    source_paths: dict[str, Path],
    bronze_dir: Path,
    batch_id: str,
    ingested_at: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Create byte-for-byte raw copies, Bronze tables and a manifest."""

    raw_dir = bronze_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    connection.execute("DROP TABLE IF EXISTS bronze_manifest")
    connection.execute(
        """
        CREATE TABLE bronze_manifest (
            source_file VARCHAR,
            source_path VARCHAR,
            bronze_copy VARCHAR,
            checksum VARCHAR,
            size_bytes BIGINT,
            row_count BIGINT,
            batch_id VARCHAR
        )
        """
    )

    for source_name, source_path in source_paths.items():
        raw_copy = raw_dir / source_path.name
        shutil.copy2(source_path, raw_copy)
        checksum = _sha256_file(source_path)
        entries.append(
            {
                "source_name": source_name,
                "file_name": source_path.name,
                "source_path": str(source_path),
                "bronze_copy": str(raw_copy),
                "checksum_sha256": checksum,
                "size_bytes": source_path.stat().st_size,
                "row_count": 0,
                "batch_id": batch_id,
            }
        )

    bookings_path = _sql_string(raw_dir / "bookings.csv")
    payments_path = _sql_string(raw_dir / "payments.jsonl")
    offers_path = _sql_string(raw_dir / "offers.csv")
    batch = _sql_string(batch_id)
    timestamp = _sql_string(ingested_at)

    connection.execute(
        f"""
        CREATE OR REPLACE TABLE bronze_bookings AS
        SELECT
            ROW_NUMBER() OVER () AS source_row_number,
            CAST(booking_id AS VARCHAR) AS booking_id,
            CAST(offer_id AS VARCHAR) AS offer_id,
            CAST(client_id AS VARCHAR) AS client_id,
            CAST(source_channel AS VARCHAR) AS source_channel,
            CAST(booking_ts AS VARCHAR) AS booking_ts,
            CAST(service_date AS VARCHAR) AS service_date,
            CAST(booking_status AS VARCHAR) AS booking_status,
            CAST(gross_amount AS VARCHAR) AS gross_amount,
            CAST(currency AS VARCHAR) AS currency,
            CAST(updated_at AS VARCHAR) AS updated_at,
            {batch} AS batch_id,
            'bookings.csv' AS source_file,
            {_sql_string(entries[0]['checksum_sha256'])} AS source_checksum,
            CAST({timestamp} AS TIMESTAMP) AS ingested_at
        FROM read_csv({bookings_path}, header = true, all_varchar = true)
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE bronze_payments AS
        SELECT
            ROW_NUMBER() OVER () AS source_row_number,
            CAST(payment_id AS VARCHAR) AS payment_id,
            CAST(booking_id AS VARCHAR) AS booking_id,
            CAST(payment_status AS VARCHAR) AS payment_status,
            CAST(amount AS VARCHAR) AS amount,
            CAST(currency AS VARCHAR) AS currency,
            CAST(paid_at AS VARCHAR) AS paid_at,
            {batch} AS batch_id,
            'payments.jsonl' AS source_file,
            {_sql_string(entries[1]['checksum_sha256'])} AS source_checksum,
            CAST({timestamp} AS TIMESTAMP) AS ingested_at
        FROM read_json_auto({payments_path}, format = 'newline_delimited')
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE bronze_offers AS
        SELECT
            ROW_NUMBER() OVER () AS source_row_number,
            CAST(offer_id AS VARCHAR) AS offer_id,
            CAST(destination AS VARCHAR) AS destination,
            CAST(commission_rate AS VARCHAR) AS commission_rate,
            TRY_CAST(active AS BOOLEAN) AS active,
            {batch} AS batch_id,
            'offers.csv' AS source_file,
            {_sql_string(entries[2]['checksum_sha256'])} AS source_checksum,
            CAST({timestamp} AS TIMESTAMP) AS ingested_at
        FROM read_csv({offers_path}, header = true, all_varchar = true)
        """
    )

    table_names = ("bronze_bookings", "bronze_payments", "bronze_offers")
    for entry, table_name in zip(entries, table_names):
        entry["row_count"] = int(
            connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        )
        connection.execute(
            "INSERT INTO bronze_manifest VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                entry["file_name"],
                entry["source_path"],
                entry["bronze_copy"],
                entry["checksum_sha256"],
                entry["size_bytes"],
                entry["row_count"],
                entry["batch_id"],
            ],
        )

    manifest_ok = all(
        Path(entry["bronze_copy"]).is_file()
        and _sha256_file(Path(entry["bronze_copy"])) == entry["checksum_sha256"]
        for entry in entries
    )
    return entries, manifest_ok


def _transform(connection: Any, *, batch_id: str, dedup_mode: str) -> None:
    """Build validation, Silver, Quarantine and Gold tables."""

    if dedup_mode not in {"latest", "oldest"}:
        raise ValueError("dedup_mode must be 'latest' or 'oldest'")
    direction = "DESC" if dedup_mode == "latest" else "ASC"
    batch = _sql_string(batch_id)
    mode = _sql_string(dedup_mode)

    connection.execute(
        """
        CREATE OR REPLACE TABLE offers_reference AS
        SELECT
            offer_id,
            destination,
            TRY_CAST(commission_rate AS DECIMAL(5, 4)) AS commission_rate,
            TRY_CAST(active AS BOOLEAN) AS active
        FROM bronze_offers
        """
    )
    booking_case = booking_validation_case("b")
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE booking_validation AS
        SELECT
            b.*,
            o.destination,
            o.commission_rate,
            o.active AS offer_active,
            {booking_case} AS validation_reason
        FROM bronze_bookings AS b
        LEFT JOIN offers_reference AS o USING (offer_id)
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE booking_ranked AS
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY booking_id
                ORDER BY TRY_CAST(updated_at AS TIMESTAMP) {direction},
                         source_row_number {direction}
            ) AS dedup_rank
        FROM booking_validation
        WHERE validation_reason IS NULL
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE current_booking_candidates AS
        SELECT
            booking_id,
            offer_id,
            SHA256(client_id) AS client_id_hash,
            UPPER(TRIM(source_channel)) AS source_channel,
            CAST(booking_ts AS TIMESTAMP) AS booking_ts,
            CAST(service_date AS DATE) AS service_date,
            UPPER(TRIM(booking_status)) AS booking_status,
            CAST(gross_amount AS DECIMAL(12, 2)) AS gross_amount,
            UPPER(TRIM(currency)) AS currency,
            CAST(updated_at AS TIMESTAMP) AS updated_at,
            destination,
            commission_rate,
            {batch} AS batch_id
        FROM booking_ranked
        WHERE dedup_rank = 1
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE superseded_bookings AS
        SELECT
            booking_id,
            offer_id,
            SHA256(client_id) AS client_id_hash,
            UPPER(TRIM(source_channel)) AS source_channel,
            CAST(booking_ts AS TIMESTAMP) AS booking_ts,
            CAST(service_date AS DATE) AS service_date,
            UPPER(TRIM(booking_status)) AS booking_status,
            CAST(gross_amount AS DECIMAL(12, 2)) AS gross_amount,
            UPPER(TRIM(currency)) AS currency,
            CAST(updated_at AS TIMESTAMP) AS updated_at,
            destination,
            commission_rate,
            dedup_rank,
            {mode} AS dedup_mode,
            {batch} AS batch_id
        FROM booking_ranked
        WHERE dedup_rank > 1
        """
    )

    payment_case = payment_validation_case("p")
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE payment_validation AS
        SELECT
            p.*,
            b.gross_amount AS booking_gross_amount,
            {payment_case} AS validation_reason
        FROM bronze_payments AS p
        LEFT JOIN current_booking_candidates AS b USING (booking_id)
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE silver_payments AS
        SELECT
            payment_id,
            booking_id,
            UPPER(TRIM(payment_status)) AS payment_status,
            CAST(amount AS DECIMAL(12, 2)) AS amount,
            UPPER(TRIM(currency)) AS currency,
            TRY_CAST(paid_at AS TIMESTAMP) AS paid_at,
            {batch} AS batch_id
        FROM payment_validation
        WHERE validation_reason IS NULL
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE latest_payment_per_booking AS
        SELECT * EXCLUDE (payment_rank)
        FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY booking_id
                    ORDER BY paid_at DESC NULLS LAST, payment_id DESC
                ) AS payment_rank
            FROM silver_payments
        )
        WHERE payment_rank = 1
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE current_booking_outcome AS
        SELECT
            b.*,
            CASE
                WHEN b.booking_status = 'CONFIRMED' AND p.booking_id IS NULL
                    THEN 'MISSING_PAYMENT'
                ELSE NULL
            END AS business_reason
        FROM current_booking_candidates AS b
        LEFT JOIN latest_payment_per_booking AS p USING (booking_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE silver_bookings AS
        SELECT * EXCLUDE (business_reason)
        FROM current_booking_outcome
        WHERE business_reason IS NULL
        """
    )

    connection.execute(
        f"""
        CREATE OR REPLACE TABLE quarantine_records AS
        SELECT
            'bookings' AS source_entity,
            source_row_number,
            COALESCE(NULLIF(booking_id, ''), 'BOOKING_ROW_' || source_row_number)
                AS record_id,
            validation_reason AS reason_code,
            'Row-level contract validation failed' AS details,
            {batch} AS batch_id,
            source_file
        FROM booking_validation
        WHERE validation_reason IS NOT NULL

        UNION ALL

        SELECT
            'bookings' AS source_entity,
            CAST(NULL AS BIGINT) AS source_row_number,
            booking_id AS record_id,
            business_reason AS reason_code,
            'Current CONFIRMED booking has no usable payment' AS details,
            {batch} AS batch_id,
            'bookings.csv' AS source_file
        FROM current_booking_outcome
        WHERE business_reason IS NOT NULL

        UNION ALL

        SELECT
            'payments' AS source_entity,
            source_row_number,
            COALESCE(NULLIF(payment_id, ''), 'PAYMENT_ROW_' || source_row_number)
                AS record_id,
            validation_reason AS reason_code,
            CASE
                WHEN validation_reason = 'AMOUNT_MISMATCH'
                    THEN 'Payment amount differs from current booking amount'
                WHEN validation_reason = 'MISSING_REQUIRED' AND booking_gross_amount IS NULL
                    THEN 'Payment references an unknown or unusable booking'
                ELSE 'Row-level contract validation failed'
            END AS details,
            {batch} AS batch_id,
            source_file
        FROM payment_validation
        WHERE validation_reason IS NOT NULL
        """
    )

    # This detail table is an auditable intermediate, not the published Gold KPI.
    # It deliberately excludes client identifiers, including their hashes.
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE gold_revenue_detail AS
        SELECT
            b.booking_id,
            p.payment_id,
            b.service_date AS business_date,
            b.destination,
            b.booking_status,
            p.payment_status,
            b.gross_amount,
            b.commission_rate,
            {batch} AS batch_id
        FROM silver_bookings AS b
        JOIN latest_payment_per_booking AS p USING (booking_id)
        WHERE b.booking_status = 'CONFIRMED'
          AND p.payment_status = 'PAID'
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE gold_daily_revenue AS
        SELECT
            business_date,
            destination,
            ROUND(SUM(gross_amount), 2) AS gross_revenue_eur,
            ROUND(SUM(gross_amount * commission_rate), 2)
                AS commission_revenue_eur,
            ROUND(
                SUM(gross_amount)
                - SUM(gross_amount * commission_rate),
                2
            ) AS net_revenue_eur,
            COUNT(DISTINCT booking_id) AS confirmed_bookings,
            {batch} AS batch_id
        FROM gold_revenue_detail
        GROUP BY business_date, destination
        ORDER BY business_date, destination
        """
    )


def _manifest_payload(
    *,
    batch_id: str,
    created_at: str,
    entries: list[dict[str, Any]],
    project_root: Path,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "created_at_utc": created_at,
        "immutable_raw_copy_verified": True,
        "files": [
            {
                "source_name": entry["source_name"],
                "file_name": entry["file_name"],
                "source_path": _relative(Path(entry["source_path"]), project_root),
                "bronze_copy": _relative(Path(entry["bronze_copy"]), project_root),
                "checksum_sha256": entry["checksum_sha256"],
                "size_bytes": entry["size_bytes"],
                "row_count": entry["row_count"],
            }
            for entry in entries
        ],
    }


def _scalar(connection: Any, sql: str) -> Any:
    return connection.execute(sql).fetchone()[0]


def _collect_metrics(
    connection: Any,
    *,
    duration_seconds: float,
) -> dict[str, Any]:
    raw_bookings = int(_scalar(connection, "SELECT COUNT(*) FROM bronze_bookings"))
    raw_payments = int(_scalar(connection, "SELECT COUNT(*) FROM bronze_payments"))
    raw_offers = int(_scalar(connection, "SELECT COUNT(*) FROM bronze_offers"))
    current_bookings = int(_scalar(connection, "SELECT COUNT(*) FROM silver_bookings"))
    superseded = int(_scalar(connection, "SELECT COUNT(*) FROM superseded_bookings"))
    quarantined_bookings = int(
        _scalar(
            connection,
            "SELECT COUNT(*) FROM quarantine_records WHERE source_entity = 'bookings'",
        )
    )
    quarantined_total = int(
        _scalar(connection, "SELECT COUNT(*) FROM quarantine_records")
    )
    silver_payments = int(_scalar(connection, "SELECT COUNT(*) FROM silver_payments"))
    gold_rows = int(_scalar(connection, "SELECT COUNT(*) FROM gold_daily_revenue"))
    reconciliation_difference = (
        raw_bookings - current_bookings - superseded - quarantined_bookings
    )
    gold_sum = float(
        _scalar(
            connection,
            "SELECT COALESCE(SUM(gross_revenue_eur), 0) FROM gold_daily_revenue",
        )
    )
    gold_rows_ordered = connection.execute(
        """
        SELECT business_date, destination, gross_revenue_eur,
               commission_revenue_eur, net_revenue_eur, confirmed_bookings,
               batch_id
        FROM gold_daily_revenue
        ORDER BY business_date, destination
        """
    ).fetchall()
    reason_rows = connection.execute(
        """
        SELECT reason_code, COUNT(*)
        FROM quarantine_records
        GROUP BY reason_code
        ORDER BY reason_code
        """
    ).fetchall()

    return {
        "source_rows": {
            "bookings": raw_bookings,
            "payments": raw_payments,
            "offers": raw_offers,
        },
        "silver_rows": {
            "bookings": current_bookings,
            "payments": silver_payments,
        },
        "superseded_bookings": superseded,
        "quarantine_rows": quarantined_total,
        "quarantine_reasons": {reason: int(count) for reason, count in reason_rows},
        "gold_rows": gold_rows,
        "gold_gross_revenue_eur": round(gold_sum, 2),
        "gold_hash_sha256": stable_rows_hash(gold_rows_ordered),
        "reconciliation": {
            "raw_bookings": raw_bookings,
            "current_bookings": current_bookings,
            "superseded_bookings": superseded,
            "quarantined_bookings": quarantined_bookings,
            "difference": reconciliation_difference,
        },
        "success_rate_percent": round(
            100.0 * (raw_bookings - quarantined_bookings) / raw_bookings,
            2,
        )
        if raw_bookings
        else 100.0,
        "duration_seconds": round(duration_seconds, 4),
        "throughput_booking_rows_per_second": round(
            raw_bookings / duration_seconds, 2
        )
        if duration_seconds > 0
        else None,
    }


def _idempotence_check(
    previous_report: dict[str, Any] | None,
    *,
    source_fingerprint: str,
    dedup_mode: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    previous_run = (previous_report or {}).get("run", {})
    previous_metrics = (previous_report or {}).get("metrics", {})
    comparable = (
        previous_run.get("source_fingerprint_sha256") == source_fingerprint
        and previous_run.get("dedup_mode") == dedup_mode
    )
    if not comparable:
        return {
            "id": "AC09",
            "name": "Same-batch idempotence",
            "status": "NOT_EVALUATED",
            "severity": "HIGH",
            "actual": "No comparable previous execution",
            "expected": "Run the same command a second time",
            "evidence": "Gold count, sum and hash are stored for the next run",
        }

    same = all(
        previous_metrics.get(key) == metrics.get(key)
        for key in ("gold_rows", "gold_gross_revenue_eur", "gold_hash_sha256")
    )
    return make_check(
        "AC09",
        "Same-batch idempotence",
        same,
        "HIGH",
        {
            "rows": metrics["gold_rows"],
            "gross": metrics["gold_gross_revenue_eur"],
            "hash": metrics["gold_hash_sha256"],
        },
        {
            "rows": previous_metrics.get("gold_rows"),
            "gross": previous_metrics.get("gold_gross_revenue_eur"),
            "hash": previous_metrics.get("gold_hash_sha256"),
        },
        "Compared with the previous run of the same batch, sources and mode",
    )


def _store_quality_checks(connection: Any, checks: Iterable[dict[str, Any]]) -> None:
    connection.execute("DROP TABLE IF EXISTS quality_checks")
    connection.execute(
        """
        CREATE TABLE quality_checks (
            check_id VARCHAR,
            check_name VARCHAR,
            status VARCHAR,
            severity VARCHAR,
            actual_json VARCHAR,
            expected_json VARCHAR,
            evidence VARCHAR
        )
        """
    )
    for check in checks:
        connection.execute(
            "INSERT INTO quality_checks VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                check["id"],
                check["name"],
                check["status"],
                check["severity"],
                json.dumps(check.get("actual"), ensure_ascii=False, default=str),
                json.dumps(check.get("expected"), ensure_ascii=False, default=str),
                check["evidence"],
            ],
        )


def run_pipeline(
    project_root: str | Path | None = None,
    *,
    batch_id: str = DEFAULT_BATCH_ID,
    dedup_mode: str = "latest",
    mode: str | None = None,
) -> dict[str, Any]:
    """Execute the complete local pipeline and return paths plus metrics.

    Parameters are usable both by pytest and by the CLI.  ``mode='fixed'`` maps
    to ``dedup_mode='latest'``; ``mode='buggy'`` maps to ``'oldest'``.
    """

    if mode is not None:
        mode_mapping = {"fixed": "latest", "buggy": "oldest"}
        if mode not in mode_mapping:
            raise ValueError("mode must be 'fixed' or 'buggy'")
        dedup_mode = mode_mapping[mode]
    if dedup_mode not in {"latest", "oldest"}:
        raise ValueError("dedup_mode must be 'latest' or 'oldest'")

    root = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else _default_project_root()
    )
    source_dir = root / "data/source"
    source_paths = _required_sources(source_dir)
    _validate_contracts(source_paths)

    bronze_dir = root / "data/bronze" / batch_id
    silver_dir = root / "data/silver" / batch_id
    quarantine_dir = root / "data/quarantine" / batch_id
    gold_dir = root / "data/gold" / batch_id
    report_dir = root / "reports" / batch_id
    for directory in (
        bronze_dir,
        silver_dir,
        quarantine_dir,
        gold_dir,
        report_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    manifest_path = bronze_dir / "manifest.json"
    silver_bookings_path = silver_dir / "bookings.parquet"
    silver_payments_path = silver_dir / "payments.parquet"
    superseded_path = silver_dir / "superseded_bookings.parquet"
    quarantine_path = quarantine_dir / "records.parquet"
    gold_path = gold_dir / "daily_revenue.parquet"
    quality_report_path = report_dir / "quality_report.json"
    database_path = root / "data/lakequality.duckdb"

    previous_report = load_previous_report(quality_report_path)
    started = time.perf_counter()
    run_timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    connection = duckdb.connect(str(database_path))
    try:
        entries, manifest_ok = _prepare_bronze(
            connection,
            source_paths=source_paths,
            bronze_dir=bronze_dir,
            batch_id=batch_id,
            ingested_at=run_timestamp,
        )
        _transform(connection, batch_id=batch_id, dedup_mode=dedup_mode)

        # Evidence files contain ordered rows to make screenshots and hashes stable.
        _copy_to_parquet(
            connection,
            "SELECT * FROM bronze_bookings ORDER BY source_row_number",
            bronze_dir / "bookings.parquet",
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM bronze_payments ORDER BY source_row_number",
            bronze_dir / "payments.parquet",
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM bronze_offers ORDER BY source_row_number",
            bronze_dir / "offers.parquet",
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM silver_bookings ORDER BY booking_id",
            silver_bookings_path,
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM silver_payments ORDER BY payment_id",
            silver_payments_path,
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM superseded_bookings ORDER BY booking_id, dedup_rank",
            superseded_path,
        )
        _copy_to_parquet(
            connection,
            """SELECT * FROM quarantine_records
               ORDER BY source_entity, source_row_number NULLS LAST, record_id""",
            quarantine_path,
        )
        _copy_to_parquet(
            connection,
            "SELECT * FROM gold_daily_revenue ORDER BY business_date, destination",
            gold_path,
        )

        manifest = _manifest_payload(
            batch_id=batch_id,
            created_at=run_timestamp,
            entries=entries,
            project_root=root,
        )
        manifest["immutable_raw_copy_verified"] = manifest_ok
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        duration = time.perf_counter() - started
        metrics = _collect_metrics(connection, duration_seconds=duration)
        connection.execute(
            """
            CREATE OR REPLACE TABLE quality_summary AS
            SELECT
                (SELECT COUNT(*) FROM bronze_bookings) AS raw_count,
                (SELECT COUNT(*) FROM silver_bookings) AS accepted_count,
                (SELECT COUNT(*) FROM superseded_bookings) AS superseded_count,
                (SELECT COUNT(*) FROM quarantine_records
                 WHERE source_entity = 'bookings') AS quarantined_count,
                (SELECT COUNT(*) FROM bronze_bookings)
                  - (SELECT COUNT(*) FROM silver_bookings)
                  - (SELECT COUNT(*) FROM superseded_bookings)
                  - (SELECT COUNT(*) FROM quarantine_records
                     WHERE source_entity = 'bookings') AS reconciliation_delta
            """
        )
        source_fingerprint = hashlib.sha256(
            "|".join(entry["checksum_sha256"] for entry in entries).encode("ascii")
        ).hexdigest()
        checks = evaluate_quality(
            connection,
            manifest_ok=manifest_ok,
            reconciliation_difference=metrics["reconciliation"]["difference"],
        )
        checks.append(
            _idempotence_check(
                previous_report,
                source_fingerprint=source_fingerprint,
                dedup_mode=dedup_mode,
                metrics=metrics,
            )
        )
        checks.append(
            make_check(
                "AC11",
                "Quality report contains required operational metrics",
                all(
                    key in metrics
                    for key in (
                        "source_rows",
                        "quarantine_reasons",
                        "superseded_bookings",
                        "reconciliation",
                        "success_rate_percent",
                        "duration_seconds",
                    )
                ),
                "HIGH",
                "metrics collected",
                "volumes, reasons, duplicates, reconciliation, rate, duration",
                _relative(quality_report_path, root),
            )
        )
        if metrics["source_rows"]["bookings"] >= 100_000:
            performance_passed = (
                metrics["duration_seconds"] < 30
                and metrics["reconciliation"]["difference"] == 0
            )
            checks.append(
                make_check(
                    "AC13",
                    "Laboratory performance baseline for 100k+ rows",
                    performance_passed,
                    "MEDIUM",
                    metrics["duration_seconds"],
                    "< 30 seconds and reconciliation difference = 0",
                    "Local machine measurement; simulated threshold",
                )
            )
        else:
            checks.append(
                {
                    "id": "AC13",
                    "name": "Laboratory performance baseline for 100k+ rows",
                    "status": "NOT_EVALUATED",
                    "severity": "MEDIUM",
                    "actual": metrics["source_rows"]["bookings"],
                    "expected": ">= 100000 booking rows",
                    "evidence": "Generate 100000 rows to execute this baseline",
                }
            )

        decision = quality_gate_decision(checks)
        report = {
            "project": "LakeQuality - Datalake Reservations",
            "disclaimer": (
                "Personal simulation using 100% synthetic data; it does not "
                "represent Sopra Steria, Nooeh or client systems."
            ),
            "run": {
                "batch_id": batch_id,
                "generated_at_utc": run_timestamp,
                "execution_mode": "fixed" if dedup_mode == "latest" else "buggy",
                "dedup_mode": dedup_mode,
                "source_fingerprint_sha256": source_fingerprint,
            },
            "metrics": metrics,
            "checks": checks,
            "summary": {
                "passed": sum(check["status"] == "PASS" for check in checks),
                "failed": sum(check["status"] == "FAIL" for check in checks),
                "not_evaluated": sum(
                    check["status"] == "NOT_EVALUATED" for check in checks
                ),
                "decision": decision,
            },
        }
        quality_report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        _store_quality_checks(connection, checks)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    paths = {
        "database": database_path,
        "bronze_manifest": manifest_path,
        "silver_bookings": silver_bookings_path,
        "silver_payments": silver_payments_path,
        "superseded_bookings": superseded_path,
        "quarantine": quarantine_path,
        "gold": gold_path,
        "quality_report": quality_report_path,
    }
    result: dict[str, Any] = {
        "paths": paths,
        "metrics": metrics,
        "checks": checks,
        "decision": decision,
        "batch_id": batch_id,
        "dedup_mode": dedup_mode,
    }
    # Convenient aliases retained for simple tests and notebook usage.
    result.update(paths)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local LakeQuality Datalake pipeline."
    )
    parser.add_argument(
        "--mode",
        choices=("fixed", "buggy"),
        default="fixed",
        help="fixed = latest-wins; buggy = deliberately oldest-wins",
    )
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Default: repository root inferred from this module",
    )
    parser.add_argument(
        "--fail-on-quality",
        action="store_true",
        help="Return exit code 2 when the quality decision is NO-GO",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_pipeline(
        args.project_root,
        batch_id=args.batch_id,
        mode=args.mode,
    )
    metrics = result["metrics"]
    print(f"LakeQuality batch: {result['batch_id']}")
    print(f"  mode           : {args.mode} ({result['dedup_mode']}-wins)")
    print(f"  source bookings: {metrics['source_rows']['bookings']}")
    print(f"  Silver bookings: {metrics['silver_rows']['bookings']}")
    print(f"  quarantine     : {metrics['quarantine_rows']}")
    print(f"  reconciliation : {metrics['reconciliation']['difference']}")
    print(f"  duration       : {metrics['duration_seconds']} s")
    print(f"  decision       : {result['decision']}")
    print(f"  report         : {result['quality_report']}")
    if args.fail_on_quality and result["decision"] == "NO-GO":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
