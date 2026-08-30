"""Laboratory-only performance baseline; this is not a client SLA (AC13)."""

import os
import time
from pathlib import Path
import sys

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_data import generate_data
from src.pipeline import run_pipeline


def test_batch_performance_laboratory_baseline(tmp_path: Path) -> None:
    rows = int(os.getenv("LAKEQUALITY_PERF_ROWS", "100000"))
    threshold_seconds = float(os.getenv("LAKEQUALITY_PERF_THRESHOLD_SECONDS", "30"))
    project_root = tmp_path / "performance-case"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=rows,
        seed=2026,
    )

    started_at = time.perf_counter()
    result = run_pipeline(
        project_root=project_root,
        batch_id="BATCH_PERFORMANCE",
        dedup_mode="latest",
    )
    elapsed_seconds = time.perf_counter() - started_at

    with duckdb.connect(str(project_root / "data" / "lakequality.duckdb"), read_only=True) as db:
        raw_count = db.execute("SELECT COUNT(*) FROM bronze_bookings").fetchone()[0]
        classified_count = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM silver_bookings)
              + (SELECT COUNT(*) FROM superseded_bookings)
              + (SELECT COUNT(*) FROM quarantine_records WHERE source_entity = 'bookings')
            """
        ).fetchone()[0]

    print(
        "LABORATORY BASELINE — not a client SLA: "
        f"requested_rows={rows}, raw_rows={raw_count}, "
        f"elapsed={elapsed_seconds:.3f}s, threshold={threshold_seconds:.3f}s, "
        f"metrics={result.get('metrics', {})}"
    )
    assert raw_count == classified_count
    assert elapsed_seconds < threshold_seconds, (
        "Laboratory baseline exceeded: "
        f"{elapsed_seconds:.3f}s >= {threshold_seconds:.3f}s for {rows} requested rows."
    )
