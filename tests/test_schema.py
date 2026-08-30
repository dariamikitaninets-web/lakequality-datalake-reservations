"""Contract tests for the three synthetic source feeds (AC02 / R04)."""

from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generate_data import generate_data
from src.pipeline import run_pipeline


BOOKING_COLUMNS = {
    "booking_id",
    "offer_id",
    "client_id",
    "source_channel",
    "booking_ts",
    "service_date",
    "booking_status",
    "gross_amount",
    "currency",
    "updated_at",
}
PAYMENT_COLUMNS = {
    "payment_id",
    "booking_id",
    "payment_status",
    "amount",
    "currency",
    "paid_at",
}
OFFER_COLUMNS = {"offer_id", "destination", "commission_rate", "active"}


def _source_path(generated: dict, key: str, default: Path) -> Path:
    """Accept both flat and nested path dictionaries from the generator."""
    candidate = generated.get(key) or generated.get("paths", {}).get(key)
    return Path(candidate) if candidate else default


def test_generated_sources_follow_the_declared_contract(tmp_path: Path) -> None:
    source_dir = tmp_path / "data" / "source"
    generated = generate_data(output_dir=source_dir, booking_count=80, seed=2026)

    bookings_path = _source_path(generated, "bookings", source_dir / "bookings.csv")
    payments_path = _source_path(generated, "payments", source_dir / "payments.jsonl")
    offers_path = _source_path(generated, "offers", source_dir / "offers.csv")

    bookings = pd.read_csv(bookings_path)
    payments = pd.read_json(payments_path, lines=True)
    offers = pd.read_csv(offers_path)

    assert set(bookings.columns) == BOOKING_COLUMNS
    assert set(payments.columns) == PAYMENT_COLUMNS
    assert set(offers.columns) == OFFER_COLUMNS
    assert not bookings.empty and not payments.empty and not offers.empty

    # Invalid business rows are intentionally present, but the physical contract
    # itself must remain parseable.
    assert pd.to_datetime(bookings["updated_at"], utc=True, errors="coerce").notna().all()
    assert pd.to_datetime(bookings["booking_ts"], utc=True, errors="coerce").notna().all()
    assert pd.to_numeric(offers["commission_rate"], errors="coerce").notna().all()


def test_missing_required_column_stops_the_batch_with_a_clear_error(tmp_path: Path) -> None:
    project_root = tmp_path / "schema-drift-case"
    source_dir = project_root / "data" / "source"
    generated = generate_data(output_dir=source_dir, booking_count=40, seed=7)
    bookings_path = _source_path(generated, "bookings", source_dir / "bookings.csv")

    bookings = pd.read_csv(bookings_path).drop(columns=["updated_at"])
    bookings.to_csv(bookings_path, index=False)

    with pytest.raises((ValueError, KeyError), match=r"(?i)(updated_at|required|schema|column)"):
        run_pipeline(
            project_root=project_root,
            batch_id="BATCH_SCHEMA_DRIFT",
            dedup_mode="latest",
        )
