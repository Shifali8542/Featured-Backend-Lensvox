"""
Inventory DB models.

InventoryRecord  – current stock level per product + batch + location.
StockMovement    – append-only audit log of every stock change.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class MovementType(str, enum.Enum):
    GOODS_RECEIPT = "GOODS_RECEIPT"
    GOODS_ISSUE = "GOODS_ISSUE"
    ADJUSTMENT_POSITIVE = "ADJUSTMENT_POSITIVE"
    ADJUSTMENT_NEGATIVE = "ADJUSTMENT_NEGATIVE"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    RETURN = "RETURN"
    WRITE_OFF = "WRITE_OFF"


class InventoryRecord(Base):
    """
    Current quantity on hand for a product + batch + storage location.
    Updated atomically when a GR is finalised.
    """

    __tablename__ = "inventory_records"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "batch_number", "storage_location",
            name="uq_inventory_product_batch_location",
        ),
        Index("ix_inv_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_location: Mapped[str] = mapped_column(
        String(100), nullable=False, default="DEFAULT"
    )
    quantity_on_hand: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    unit_of_measure: Mapped[str] = mapped_column(String(50), nullable=False, default="EA")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryRecord product={self.product_id} "
            f"batch={self.batch_number} qty={self.quantity_on_hand}>"
        )


class StockMovement(Base):
    """Immutable audit trail – one record per stock change."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_sm_product_id", "product_id"),
        Index("ix_sm_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    movement_type: Mapped[MovementType] = mapped_column(
        SAEnum(MovementType, name="movement_type_enum"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="GR number, transfer ref, etc."
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
