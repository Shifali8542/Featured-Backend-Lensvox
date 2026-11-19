"""
Integration tests for the complete Goods Receipt workflow:
  Scan label → Match PO → Record GR → Validate → Finalise → Inventory updated.
"""

import pytest
import uuid


async def _create_product(client, sku: str, name: str) -> str:
    r = await client.post("/api/v1/catalogue/products", json={
        "sku": sku, "name": name, "unit_of_measure": "EA"
    })
    assert r.status_code == 201
    return r.json()["data"]["id"]


async def _link_code(client, product_id: str, code: str) -> None:
    await client.post(f"/api/v1/catalogue/products/{product_id}/codes", json={
        "code": code, "code_type": "EAN13", "is_primary": True
    })


async def _create_po(client, po_number: str, product_id: str, qty: float) -> str:
    r = await client.post("/api/v1/purchase-orders", json={
        "po_number": po_number,
        "supplier_name": "Test Supplier",
        "lines": [{"product_id": product_id, "quantity_ordered": qty}],
    })
    assert r.status_code == 201
    po_id = r.json()["data"]["id"]
    # Approve the PO so it's matchable
    await client.patch(f"/api/v1/purchase-orders/{po_id}/status?status=OPEN")
    return po_id


@pytest.mark.asyncio
async def test_full_gr_workflow_no_shortage(client):
    """Happy path: scan exact quantity → no discrepancy → inventory updated."""

    product_id = await _create_product(client, "GR-PROD-001", "GR Test Product")
    await _link_code(client, product_id, "1234567890001")
    po_id = await _create_po(client, "PO-GR-001", product_id, 100.0)

    # Scan label
    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": "1234567890001",
        "label_type_hint": "PLAIN_BARCODE",
        "po_id": po_id,
    })
    assert scan_r.status_code == 200
    parsed = scan_r.json()["data"]
    assert parsed["product_id"] == product_id

    # Create GR
    gr_r = await client.post("/api/v1/goods-receipts", json={
        "purchase_order_id": po_id,
        "lines": [{
            "parsed_label": parsed,
            "quantity_received": 100.0,
            "unit_of_measure": "EA",
            "po_id": po_id,
        }],
    })
    assert gr_r.status_code == 201
    gr = gr_r.json()["data"]
    assert gr["has_discrepancies"] is False
    gr_id = gr["id"]

    # Finalise
    fin_r = await client.post(f"/api/v1/goods-receipts/{gr_id}/finalise", json={})
    assert fin_r.status_code == 200
    assert fin_r.json()["data"]["status"] == "FINALISED"

    # Check inventory
    inv_r = await client.get(f"/api/v1/inventory/products/{product_id}")
    assert inv_r.status_code == 200
    records = inv_r.json()["data"]
    total = sum(r["quantity_on_hand"] for r in records)
    assert total == 100.0


@pytest.mark.asyncio
async def test_full_gr_workflow_with_shortage(client):
    """Receive 70 against PO of 100 → shortage discrepancy flagged."""

    product_id = await _create_product(client, "GR-PROD-002", "Shortage Product")
    await _link_code(client, product_id, "9876543210001")
    po_id = await _create_po(client, "PO-GR-002", product_id, 100.0)

    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": "9876543210001",
        "label_type_hint": "PLAIN_BARCODE",
        "po_id": po_id,
    })
    parsed = scan_r.json()["data"]

    gr_r = await client.post("/api/v1/goods-receipts", json={
        "purchase_order_id": po_id,
        "lines": [{
            "parsed_label": parsed,
            "quantity_received": 70.0,
            "unit_of_measure": "EA",
            "po_id": po_id,
        }],
    })
    assert gr_r.status_code == 201
    gr = gr_r.json()["data"]
    assert gr["has_discrepancies"] is True
    disc_types = [d["discrepancy_type"] for l in gr["lines"] for d in l["discrepancies"]]
    assert "SHORTAGE" in disc_types


@pytest.mark.asyncio
async def test_gr_summary_endpoint(client):
    product_id = await _create_product(client, "GR-PROD-003", "Summary Product")
    await _link_code(client, product_id, "1111111110001")
    po_id = await _create_po(client, "PO-GR-003", product_id, 50.0)

    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": "1111111110001",
        "label_type_hint": "PLAIN_BARCODE",
        "po_id": po_id,
    })
    parsed = scan_r.json()["data"]

    gr_r = await client.post("/api/v1/goods-receipts", json={
        "purchase_order_id": po_id,
        "lines": [{"parsed_label": parsed, "quantity_received": 50.0, "po_id": po_id}],
    })
    gr_id = gr_r.json()["data"]["id"]

    summary_r = await client.get(f"/api/v1/goods-receipts/{gr_id}/summary")
    assert summary_r.status_code == 200
    summary = summary_r.json()["data"]
    assert summary["total_lines"] == 1
    assert summary["total_quantity_received"] == 50.0


@pytest.mark.asyncio
async def test_finalise_already_finalised_returns_conflict(client):
    product_id = await _create_product(client, "GR-PROD-004", "Double Finalise")
    await _link_code(client, product_id, "2222222220001")
    po_id = await _create_po(client, "PO-GR-004", product_id, 10.0)

    scan_r = await client.post("/api/v1/labels/scan", json={
        "raw_data": "2222222220001", "label_type_hint": "PLAIN_BARCODE", "po_id": po_id,
    })
    parsed = scan_r.json()["data"]
    gr_r = await client.post("/api/v1/goods-receipts", json={
        "purchase_order_id": po_id,
        "lines": [{"parsed_label": parsed, "quantity_received": 10.0, "po_id": po_id}],
    })
    gr_id = gr_r.json()["data"]["id"]

    r1 = await client.post(f"/api/v1/goods-receipts/{gr_id}/finalise", json={})
    assert r1.status_code == 200

    r2 = await client.post(f"/api/v1/goods-receipts/{gr_id}/finalise", json={})
    assert r2.status_code == 409  # Conflict – already finalised
