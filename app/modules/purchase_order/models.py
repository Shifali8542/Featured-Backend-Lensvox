"""
Purchase Order DB models.

PurchaseOrder  – PO header (supplier, delivery date, status, …)
POLine         – One line per ordered product (qty ordered, unit price, …)
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class POStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    OPEN = "OPEN"           # awaiting delivery
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    FULLY_RECEIVED = "FULLY_RECEIVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (Index("ix_po_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    po_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[POStatus] = mapped_column(
        SAEnum(POStatus, name="po_status_enum"),
        default=POStatus.DRAFT,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    lines: Mapped[list["POLine"]] = relationship(
        "POLine", back_populates="purchase_order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder po_number={self.po_number!r} status={self.status}>"


class POLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        Index("ix_po_lines_po_id", "purchase_order_id"),
        Index("ix_po_lines_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(nullable=False, default=1)
    quantity_ordered: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    quantity_received: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=0
    )
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit_of_measure: Mapped[str] = mapped_column(String(50), nullable=False, default="EA")
    is_fully_received: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="lines")

    def __repr__(self) -> str:
        return (
            f"<POLine product_id={self.product_id} "
            f"ordered={self.quantity_ordered} received={self.quantity_received}>"
        )
