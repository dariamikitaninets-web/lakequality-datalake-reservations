"""End-to-end quality gate, including the controlled BUG-001 cycle."""

import os
from pathlib import Path
import sys

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_data import generate_data
from src.pipeline import run_pipeline


def _dedup_mode_from_environment() -> str:
    mode = os.getenv("LAKEQUALITY_MODE", "fixed").strip().lower()
    aliases = {"fixed": "latest", "latest": "latest", "buggy": "oldest", "oldest": "oldest"}
    if mode not in aliases:
        raise ValueError(f"Unsupported LAKEQUALITY_MODE={mode!r}; use fixed or buggy.")
    return aliases[mode]


def test_latest_booking_version_is_retained_bug_001(tmp_path: Path) -> None:
    """This is the only test expected to fail in the controlled buggy mode."""
    project_root = tmp_path / "latest-wins-case"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=120,
        seed=2026,
    )
    dedup_mode = _dedup_mode_from_environment()
    run_pipeline(
        project_root=project_root,
        batch_id="BATCH_BUG_001",
        dedup_mode=dedup_mode,
    )

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        mismatches = db.execute(
            """
            WITH accepted_versions AS (
                SELECT booking_id, updated_at FROM silver_bookings
                UNION ALL
                SELECT booking_id, updated_at FROM superseded_bookings
            ), latest_source AS (
                SELECT booking_id, MAX(updated_at) AS expected_updated_at
                FROM accepted_versions
                GROUP BY booking_id
            )
            SELECT
                s.booking_id,
                l.expected_updated_at,
                s.updated_at AS actual_updated_at
            FROM silver_bookings s
            JOIN latest_source l USING (booking_id)
            WHERE s.updated_at <> l.expected_updated_at
            ORDER BY s.booking_id
            """
        ).fetchall()

    assert mismatches == [], (
        "BUG-001 — latest-wins violated: Silver retained an older booking version. "
        f"Evidence (booking_id, expected, actual): {mismatches[:5]}"
    )


def test_every_booking_row_is_reconciled_end_to_end(tmp_path: Path) -> None:
    project_root = tmp_path / "reconciliation-case"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=150,
        seed=11,
    )
    run_pipeline(
        project_root=project_root,
        batch_id="BATCH_RECONCILIATION",
        dedup_mode="latest",
    )

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        raw_count = db.execute("SELECT COUNT(*) FROM bronze_bookings").fetchone()[0]
        current_count = db.execute("SELECT COUNT(*) FROM silver_bookings").fetchone()[0]
        superseded_count = db.execute(
            "SELECT COUNT(*) FROM superseded_bookings"
        ).fetchone()[0]
        quarantined_count = db.execute(
            "SELECT COUNT(*) FROM quarantine_records WHERE source_entity = 'bookings'"
        ).fetchone()[0]

    classified_count = current_count + superseded_count + quarantined_count
    assert raw_count == classified_count, (
        "AC03 reconciliation gap: "
        f"raw={raw_count}, current={current_count}, superseded={superseded_count}, "
        f"quarantined={quarantined_count}, gap={raw_count - classified_count}"
    )


def test_bronze_manifest_proves_all_three_inputs_were_ingested(tmp_path: Path) -> None:
    project_root = tmp_path / "manifest-case"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=50,
        seed=21,
    )
    run_pipeline(
        project_root=project_root,
        batch_id="BATCH_MANIFEST",
        dedup_mode="latest",
    )

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        manifest = db.execute(
            """
            SELECT source_file, batch_id, checksum
            FROM bronze_manifest
            ORDER BY source_file
            """
        ).fetchall()

    assert len(manifest) == 3
    assert {row[0] for row in manifest} == {"bookings.csv", "offers.csv", "payments.jsonl"}
    assert all(row[1] == "BATCH_MANIFEST" for row in manifest)
    assert all(row[2] and len(row[2]) >= 32 for row in manifest)
