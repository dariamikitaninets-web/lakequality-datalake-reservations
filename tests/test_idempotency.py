"""Idempotent replay of the same batch (AC09 / R06)."""

import hashlib
from pathlib import Path
import sys

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_data import generate_data
from src.pipeline import run_pipeline


def _gold_snapshot(database_path: Path) -> tuple[int, float, str]:
    with duckdb.connect(str(database_path), read_only=True) as db:
        gold = db.execute(
            "SELECT * FROM gold_daily_revenue ORDER BY business_date, destination"
        ).fetchdf()

    canonical = gold.to_csv(index=False, lineterminator="\n", float_format="%.6f")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    revenue = float(pd.to_numeric(gold["gross_revenue_eur"]).sum()) if not gold.empty else 0.0
    return len(gold), revenue, digest


def test_replaying_the_same_batch_does_not_change_gold(tmp_path: Path) -> None:
    project_root = tmp_path / "idempotency-case"
    database_path = project_root / "data" / "lakequality.duckdb"
    generate_data(
        output_dir=project_root / "data" / "source",
        booking_count=200,
        seed=2026,
    )

    run_pipeline(
        project_root=project_root,
        batch_id="BATCH_IDEMPOTENT",
        dedup_mode="latest",
    )
    first = _gold_snapshot(database_path)

    run_pipeline(
        project_root=project_root,
        batch_id="BATCH_IDEMPOTENT",
        dedup_mode="latest",
    )
    second = _gold_snapshot(database_path)

    assert second == first, (
        "The repeated batch changed Gold: "
        f"first=(rows={first[0]}, revenue={first[1]:.2f}, hash={first[2]}), "
        f"second=(rows={second[0]}, revenue={second[1]:.2f}, hash={second[2]})."
    )
