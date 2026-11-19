"""
Pydantic schemas for the Catalogue module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Product ───────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100, examples=["PROD-00123"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Paracetamol 500mg"])
    description: str | None = None
    unit_of_measure: str = Field(default="EA", max_length=50)
    category: str | None = None
    sub_category: str | None = None
    weight_kg: float | None = None
    volume_ml: float | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    unit_of_measure: str | None = None
    category: str | None = None
    sub_category: str | None = None
    weight_kg: float | None = None
    volume_ml: float | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    unit_of_measure: str
    category: str | None
    sub_category: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── LabelCode ─────────────────────────────────────────────────────────────────

class LabelCodeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=255)
    code_type: str = Field(default="UNKNOWN", max_length=50)
    is_primary: bool = False


class LinkBarcodeRequest(BaseModel):
    """Case F – link an unknown barcode to a product or create one."""
    unlinked_code: str = Field(..., description="The unrecognised barcode / QR value")
    code_type: str = Field(default="UNKNOWN", max_length=50)
    # Option 1: link to existing product
    existing_product_id: uuid.UUID | None = None
    # Option 2: create a new product at the same time
    new_product: ProductCreate | None = None


class LabelCodeResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    code: str
    code_type: str
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}
