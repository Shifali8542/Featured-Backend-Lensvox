"""
Business-rule validators for a GR line.
Each validator is a pure function: (inputs) → list[DiscrepancyType and messages].
Keeping validators separate from the service makes them independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.modules.goods_receipt.models import DiscrepancyType

# How many days before expiry to flag NEAR_EXPIRY
NEAR_EXPIRY_THRESHOLD_DAYS = 90


@dataclass
class DiscrepancyFlag:
    discrepancy_type: DiscrepancyType
    expected_value: str | None
    actual_value: str | None
    description: str


def validate_quantity(
    quantity_received: float,
    quantity_outstanding: float,
) -> list[DiscrepancyFlag]:
    flags: list[DiscrepancyFlag] = []
    if quantity_received < quantity_outstanding:
        shortage = quantity_outstanding - quantity_received
        flags.append(
            DiscrepancyFlag(
                discrepancy_type=DiscrepancyType.SHORTAGE,
                expected_value=str(quantity_outstanding),
                actual_value=str(quantity_received),
                description=f"Shortage of {shortage:.4f} units vs PO.",
            )
        )
    elif quantity_received > quantity_outstanding:
        excess = quantity_received - quantity_outstanding
        flags.append(
            DiscrepancyFlag(
                discrepancy_type=DiscrepancyType.EXCESS,
                expected_value=str(quantity_outstanding),
                actual_value=str(quantity_received),
                description=f"Excess of {excess:.4f} units over PO.",
            )
        )
    return flags


def validate_expiry(expiry_date: date | None) -> list[DiscrepancyFlag]:
    flags: list[DiscrepancyFlag] = []
    if expiry_date is None:
        return flags

    today = datetime.now(tz=timezone.utc).date()
    if expiry_date < today:
        flags.append(
            DiscrepancyFlag(
                discrepancy_type=DiscrepancyType.EXPIRED,
                expected_value=f"after {today}",
                actual_value=str(expiry_date),
                description=f"Product expired on {expiry_date}.",
            )
        )
    elif expiry_date < today + timedelta(days=NEAR_EXPIRY_THRESHOLD_DAYS):
        flags.append(
            DiscrepancyFlag(
                discrepancy_type=DiscrepancyType.NEAR_EXPIRY,
                expected_value=f"after {today + timedelta(days=NEAR_EXPIRY_THRESHOLD_DAYS)}",
                actual_value=str(expiry_date),
                description=(
                    f"Product expires within {NEAR_EXPIRY_THRESHOLD_DAYS} days "
                    f"(on {expiry_date})."
                ),
            )
        )
    return flags


def validate_product_match(
    scanned_product_id: str | None,
    po_product_id: str | None,
) -> list[DiscrepancyFlag]:
    if scanned_product_id and po_product_id and scanned_product_id != po_product_id:
        return [
            DiscrepancyFlag(
                discrepancy_type=DiscrepancyType.WRONG_PRODUCT,
                expected_value=po_product_id,
                actual_value=scanned_product_id,
                description="Scanned product does not match PO line product.",
            )
        ]
    return []


def run_all_validators(
    quantity_received: float,
    quantity_outstanding: float | None,
    expiry_date: date | None,
    scanned_product_id: str | None,
    po_product_id: str | None,
) -> list[DiscrepancyFlag]:
    """Run all validators and aggregate flags."""
    flags: list[DiscrepancyFlag] = []

    if quantity_outstanding is not None:
        flags.extend(validate_quantity(quantity_received, quantity_outstanding))

    flags.extend(validate_expiry(expiry_date))
    flags.extend(validate_product_match(scanned_product_id, po_product_id))

    return flags
