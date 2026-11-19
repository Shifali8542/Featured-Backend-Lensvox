"""
Label Parser API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.modules.label_parser.schemas import LabelType, ParsedLabelData, ParseStatus, ScanLabelRequest
from app.modules.label_parser.service import LabelParserService
from app.modules.label_parser.ocr_service import OcrService
from app.utils.response import ok

router = APIRouter(prefix="/labels", tags=["Label Parser"])


@router.post(
    "/scan",
    response_model=dict,
    summary="Scan or manually enter a product label",
    description=(
        "Accepts a scanned label (or manual entry) and returns structured product, "
        "batch, and expiry information. Supports all 6 label cases: GS1, plain "
        "barcode, supplier QR, manual, damaged, and unknown."
    ),
    status_code=200,
)
async def scan_label(
    payload: ScanLabelRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = LabelParserService(db)
    parsed: ParsedLabelData = await service.parse(payload)
    return ok(data=parsed.model_dump(), message="Label parsed successfully.")


@router.post(
    "/ocr-scan",
    response_model=dict,
    summary="Scan a text-only label using OCR",
    description=(
        "Accepts a photo of a product label (JPEG/PNG), runs OCR to extract text, "
        "then parses the extracted text through the normal label pipeline. "
        "Use this for labels that have no barcode or QR code — only printed text."
    ),
    status_code=200,
)
async def ocr_scan_label(
    image: UploadFile = File(..., description="Photo of the label (JPEG or PNG)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Validate file type
    if image.content_type not in ("image/jpeg", "image/png", "image/jpg", "image/webp"):
        raise HTTPException(
            status_code=422,
            detail="Only JPEG and PNG images are supported.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=422, detail="Image too large. Max size is 10 MB.")

    # Run OCR — extract the best single identifier (not the whole box text)
    ocr = OcrService()
    best_id = ocr.extract_best_identifier(image_bytes)

    if not best_id:
        empty_result = ParsedLabelData(
            label_type=LabelType.UNKNOWN,
            parse_status=ParseStatus.NOT_FOUND,
            notes=["OCR could not extract any text from the image. "
                   "Try better lighting or hold the camera steady."],
        )
        return ok(data=empty_result.model_dump(), message="No text found in image.")

    # Run the best identifier through the normal label parser
    request = ScanLabelRequest(raw_data=best_id)
    service = LabelParserService(db)
    parsed: ParsedLabelData = await service.parse(request)

    # Add OCR note so the UI can show what was read
    parsed.notes = [f"OCR extracted: {best_id}"] + (parsed.notes or [])

    return ok(data=parsed.model_dump(), message="Label scanned via OCR.")


@router.get(
    "/types",
    summary="List supported label types",
    tags=["Label Parser"],
)
async def list_label_types() -> dict:
    return ok(
        data=[
            {"code": "GS1", "description": "Structured GS1 barcode or QR (Application Identifiers)"},
            {"code": "PLAIN_BARCODE", "description": "Normal product barcode (EAN-13, UPC-A, Code-128 …)"},
            {"code": "SUPPLIER_QR", "description": "Supplier-specific QR code (non-GS1, proprietary format)"},
            {"code": "MANUAL", "description": "No barcode – employee searches by name or SKU"},
            {"code": "DAMAGED", "description": "Damaged/unreadable code – employee types printed digits"},
            {"code": "UNKNOWN", "description": "Unrecognised code – catalogue action required"},
        ],
        message="Supported label types.",
    )