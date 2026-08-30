"""Generate deterministic, fully synthetic inputs for the training pipeline.

The generator creates a mostly valid dataset plus a small, documented set of
negative test rows.  Negative rows are test data, not application defects.  A
two-version booking is also included to demonstrate the controlled
oldest-versus-latest deduplication defect.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROWS = 1_000
DEFAULT_SEED = 42
MINIMUM_ROWS = 20

DESTINATIONS: tuple[tuple[str, str, str, bool], ...] = (
    ("OFF001", "Marseille", "0.1200", True),
    ("OFF002", "Aix-en-Provence", "0.1000", True),
    ("OFF003", "Avignon", "0.1400", True),
    ("OFF004", "Cassis", "0.1100", True),
    ("OFF005", "Arles", "0.1300", True),
    ("OFF006", "Nice", "0.1500", True),
    ("OFF999", "Legacy offer", "0.0900", False),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _booking_row(
    sequence: int,
    rng: random.Random,
    base_time: datetime,
) -> dict[str, str]:
    booking_time = base_time + timedelta(minutes=sequence * 7)
    service_date = (booking_time + timedelta(days=2 + sequence % 12)).date()
    offer_id = DESTINATIONS[sequence % 6][0]
    status = ("CONFIRMED", "CONFIRMED", "PENDING", "CANCELLED")[sequence % 4]
    amount = 80 + ((sequence * 37) % 920) + rng.randint(0, 99) / 100
    return {
        "booking_id": f"BKG-{sequence:06d}",
        "offer_id": offer_id,
        "client_id": f"CLI-{sequence:06d}",
        "source_channel": ("WEB", "AGENCY", "B2B_API")[sequence % 3],
        "booking_status": status,
        "booking_ts": _iso_datetime(booking_time),
        "service_date": service_date.isoformat(),
        "gross_amount": f"{amount:.2f}",
        "currency": "EUR",
        "updated_at": _iso_datetime(booking_time + timedelta(minutes=5)),
    }


def _apply_test_scenarios(bookings: list[dict[str, str]]) -> dict[str, Any]:
    """Inject deterministic scenarios into an existing list of booking rows."""

    # Rows 0 and 1 represent the same reservation.  All revenue fields stay the
    # same so the intentionally buggy mode fails only the latest-wins control.
    old_version = bookings[0]
    old_version.update(
        {
            "booking_id": "BKG-000001",
            "client_id": "CLI-OLD-000001",
            "booking_status": "CONFIRMED",
            "gross_amount": "245.50",
            "updated_at": "2026-08-01T08:05:00Z",
        }
    )
    new_version = old_version.copy()
    new_version.update(
        {
            "client_id": "CLI-000001",
            "updated_at": "2026-08-02T09:15:00Z",
        }
    )
    bookings[1] = new_version

    # Row-level negative data.  Each row has one primary expected reason.
    bookings[2]["client_id"] = ""
    bookings[3]["offer_id"] = "OFF_DOES_NOT_EXIST"
    booking_date = datetime.fromisoformat(bookings[4]["booking_ts"].replace("Z", "+00:00"))
    bookings[4]["service_date"] = (booking_date.date() - timedelta(days=1)).isoformat()
    bookings[5]["booking_status"] = "UNKNOWN"
    bookings[6]["gross_amount"] = "-15.00"
    bookings[7]["currency"] = "USD"
    bookings[8].update({"booking_status": "CONFIRMED", "gross_amount": "310.00"})
    bookings[9]["booking_status"] = "CONFIRMED"
    bookings[10]["booking_status"] = "CANCELLED"
    bookings[11]["booking_status"] = "CONFIRMED"

    return {
        "dedup_booking_id": "BKG-000001",
        "expected_latest_updated_at": "2026-08-02T09:15:00Z",
        "negative_booking_rows": {
            bookings[2]["booking_id"]: "MISSING_REQUIRED",
            bookings[3]["booking_id"]: "UNKNOWN_OFFER",
            bookings[4]["booking_id"]: "INVALID_DATE_ORDER",
            bookings[5]["booking_id"]: "INVALID_STATUS",
            bookings[6]["booking_id"]: "NEGATIVE_AMOUNT",
            bookings[7]["booking_id"]: "UNSUPPORTED_CURRENCY",
        },
        "amount_mismatch_booking_id": bookings[8]["booking_id"],
    }


def _payment_rows(
    bookings: list[dict[str, str]],
    scenarios: dict[str, Any],
) -> list[dict[str, str]]:
    by_booking: dict[str, dict[str, str]] = {}
    for booking in bookings:
        # The assignment deliberately keeps the newer occurrence of a duplicate.
        by_booking[booking["booking_id"]] = booking

    invalid_booking_ids = set(scenarios["negative_booking_rows"])
    rows: list[dict[str, str]] = []
    payment_sequence = 1
    for booking_id, booking in by_booking.items():
        if booking_id in invalid_booking_ids:
            continue
        status = {
            "CONFIRMED": "PAID",
            "PENDING": "DECLINED",
            "CANCELLED": "REFUNDED",
        }.get(booking["booking_status"], "DECLINED")
        if booking_id == bookings[9]["booking_id"]:
            status = "DECLINED"
        paid_at = datetime.fromisoformat(booking["updated_at"].replace("Z", "+00:00"))
        amount = booking["gross_amount"]
        if booking_id == scenarios["amount_mismatch_booking_id"]:
            amount = f"{float(amount) + 25:.2f}"
        rows.append(
            {
                "payment_id": f"PAY-{payment_sequence:06d}",
                "booking_id": booking_id,
                "payment_status": status,
                "amount": amount,
                "currency": "EUR",
                "paid_at": _iso_datetime(paid_at + timedelta(minutes=10)),
            }
        )
        payment_sequence += 1

    rows.append(
        {
            "payment_id": f"PAY-{payment_sequence:06d}",
            "booking_id": "BKG-ORPHAN",
            "payment_status": "PAID",
            "amount": "99.99",
            "currency": "EUR",
            "paid_at": "2026-08-03T10:00:00Z",
        }
    )
    scenarios["orphan_payment_id"] = rows[-1]["payment_id"]
    return rows


def generate_data(
    output_dir: str | Path | None = None,
    *,
    booking_count: int = DEFAULT_ROWS,
    seed: int = DEFAULT_SEED,
    rows: int | None = None,
) -> dict[str, Any]:
    """Create source files and return their paths and scenario metadata.

    ``booking_count`` means the exact number of raw rows in ``bookings.csv``.
    ``rows`` is an API alias matching the beginner-friendly CLI option.
    """

    if rows is not None:
        booking_count = rows
    if booking_count < MINIMUM_ROWS:
        raise ValueError(
            f"At least {MINIMUM_ROWS} rows are required for all test scenarios."
        )

    target = Path(output_dir) if output_dir is not None else _project_root() / "data/source"
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    base_time = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    bookings = [
        _booking_row(sequence, rng, base_time)
        for sequence in range(1, booking_count + 1)
    ]
    scenarios = _apply_test_scenarios(bookings)
    payments = _payment_rows(bookings, scenarios)

    bookings_path = target / "bookings.csv"
    payments_path = target / "payments.jsonl"
    offers_path = target / "offers.csv"
    metadata_path = target / "scenario_metadata.json"

    with bookings_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(bookings[0]))
        writer.writeheader()
        writer.writerows(bookings)

    with payments_path.open("w", encoding="utf-8", newline="\n") as stream:
        for payment in payments:
            stream.write(json.dumps(payment, ensure_ascii=False) + "\n")

    with offers_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("offer_id", "destination", "commission_rate", "active"))
        for offer_id, destination, commission_rate, active in DESTINATIONS:
            writer.writerow((offer_id, destination, commission_rate, str(active).lower()))

    metadata = {
        "generator": "LakeQuality synthetic data generator",
        "seed": seed,
        "booking_rows": len(bookings),
        "unique_booking_ids": len({row["booking_id"] for row in bookings}),
        "payment_rows": len(payments),
        "offer_rows": len(DESTINATIONS),
        "scenarios": scenarios,
        "disclaimer": "100% synthetic data; no company or client data",
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result: dict[str, Any] = {
        "bookings": bookings_path,
        "payments": payments_path,
        "offers": offers_path,
        "scenario_metadata": metadata_path,
        "metadata": metadata,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic Datalake source files."
    )
    parser.add_argument(
        "--rows",
        "--booking-count",
        type=int,
        default=DEFAULT_ROWS,
        dest="booking_count",
        help="Exact number of raw booking rows (minimum: 20).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: <project>/data/source",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = generate_data(
        args.output_dir,
        booking_count=args.booking_count,
        seed=args.seed,
    )
    metadata = result["metadata"]
    print("Synthetic source data created")
    print(f"  bookings : {result['bookings']} ({metadata['booking_rows']} rows)")
    print(f"  payments : {result['payments']} ({metadata['payment_rows']} rows)")
    print(f"  offers   : {result['offers']} ({metadata['offer_rows']} rows)")
    print(f"  scenarios: {result['scenario_metadata']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
