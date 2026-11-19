"""
Integration tests for the label scan endpoint – all 6 cases.
"""

import pytest


@pytest.mark.asyncio
async def test_scan_manual_no_product_ref_returns_not_found(client):
    response = await client.post("/api/v1/labels/scan", json={
        "manual_product_ref": "NONEXISTENT-PRODUCT",
        "label_type_hint": "MANUAL",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["label_type"] == "MANUAL"
    assert data["parse_status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_scan_manual_with_batch_and_expiry(client):
    response = await client.post("/api/v1/labels/scan", json={
        "label_type_hint": "MANUAL",
        "manual_product_ref": "GHOST-SKU",
        "manual_batch": "B-001",
        "manual_expiry": "2026-12-31",
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_scan_unknown_barcode_returns_needs_link(client):
    response = await client.post("/api/v1/labels/scan", json={
        "raw_data": "TOTALLY-UNKNOWN-BARCODE-XYZ",
        "label_type_hint": "UNKNOWN",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["label_type"] == "UNKNOWN"
    assert data["parse_status"] == "NEEDS_LINK"
    assert data["unlinked_code"] == "TOTALLY-UNKNOWN-BARCODE-XYZ"


@pytest.mark.asyncio
async def test_scan_plain_barcode_product_found(client):
    # First create a product and link the barcode
    create_r = await client.post("/api/v1/catalogue/products", json={
        "sku": "SCAN-TEST-001", "name": "Scannable Product", "unit_of_measure": "EA"
    })
    product_id = create_r.json()["data"]["id"]
    await client.post(f"/api/v1/catalogue/products/{product_id}/codes", json={
        "code": "5901234123457", "code_type": "EAN13", "is_primary": True
    })

    # Now scan it
    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": "5901234123457",
        "label_type_hint": "PLAIN_BARCODE",
    })
    assert scan_r.status_code == 200
    data = scan_r.json()["data"]
    assert data["product_id"] == product_id
    assert data["parse_status"] == "PARTIAL"  # batch/expiry still needed


@pytest.mark.asyncio
async def test_scan_supplier_json_qr_found(client):
    # Create product and link by SKU
    create_r = await client.post("/api/v1/catalogue/products", json={
        "sku": "SUP-QR-001", "name": "Supplier QR Product", "unit_of_measure": "EA"
    })
    product_id = create_r.json()["data"]["id"]
    await client.post(f"/api/v1/catalogue/products/{product_id}/codes", json={
        "code": "SUP-QR-001", "code_type": "QR"
    })

    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": '{"sku":"SUP-QR-001","batch":"B22","exp":"2026-01-15"}',
        "label_type_hint": "SUPPLIER_QR",
    })
    assert scan_r.status_code == 200
    data = scan_r.json()["data"]
    assert data["label_type"] == "SUPPLIER_QR"
    assert data["batch_number"] == "B22"


@pytest.mark.asyncio
async def test_list_label_types(client):
    response = await client.get("/api/v1/labels/types")
    assert response.status_code == 200
    types = response.json()["data"]
    codes = [t["code"] for t in types]
    assert "GS1" in codes
    assert "MANUAL" in codes
    assert "UNKNOWN" in codes
