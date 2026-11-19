"""
Catalogue DB models: Product and LabelCode.

Product  – master product record.
LabelCode – many barcodes/GTINs can map to one product (Case A–F support).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_of_measure: Mapped[str] = mapped_column(String(50), nullable=False, default="EA")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Category / classification (optional, supports future expansion)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Physical attributes
    weight_kg: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    volume_ml: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    label_codes: Mapped[list["LabelCode"]] = relationship(
        "LabelCode", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product sku={self.sku!r} name={self.name!r}>"


class LabelCode(Base):
    """
    One product can have many associated codes (EAN, GS1 GTIN, QR text, etc.).
    This table is what the label parser queries to match a scanned code
    to a catalogue product – it is the backbone of Cases A–E lookup,
    and the target of Case F 'link' action.
    """

    __tablename__ = "label_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_label_codes_code"),
        Index("ix_label_codes_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNKNOWN",
        comment="GS1_GTIN | EAN13 | UPC_A | CODE128 | QR | MANUAL",
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Case F: user who linked the code"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationship
    product: Mapped["Product"] = relationship("Product", back_populates="label_codes")

    def __repr__(self) -> str:
        return f"<LabelCode code={self.code!r} type={self.code_type!r}>"
