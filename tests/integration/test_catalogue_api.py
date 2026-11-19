"""
Integration tests for Catalogue API (products + label code linking).
"""

import pytest


@pytest.mark.asyncio
async def test_create_product(client):
    response = await client.post("/api/v1/catalogue/products", json={
        "sku": "TEST-001",
        "name": "Test Product",
        "unit_of_measure": "EA",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["sku"] == "TEST-001"


@pytest.mark.asyncio
async def test_duplicate_sku_rejected(client):
    payload = {"sku": "DUP-SKU", "name": "First", "unit_of_measure": "EA"}
    r1 = await client.post("/api/v1/catalogue/products", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/catalogue/products", json=payload)
    assert r2.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_get_product(client):
    create_r = await client.post("/api/v1/catalogue/products", json={
        "sku": "GET-001", "name": "Get Me", "unit_of_measure": "EA"
    })
    product_id = create_r.json()["data"]["id"]

    get_r = await client.get(f"/api/v1/catalogue/products/{product_id}")
    assert get_r.status_code == 200
    assert get_r.json()["data"]["id"] == product_id


@pytest.mark.asyncio
async def test_add_label_code_to_product(client):
    create_r = await client.post("/api/v1/catalogue/products", json={
        "sku": "LABEL-001", "name": "Label Product", "unit_of_measure": "EA"
    })
    product_id = create_r.json()["data"]["id"]

    code_r = await client.post(
        f"/api/v1/catalogue/products/{product_id}/codes",
        json={"code": "5901234123457", "code_type": "EAN13", "is_primary": True},
    )
    assert code_r.status_code == 201
    assert code_r.json()["data"]["code"] == "5901234123457"


@pytest.mark.asyncio
async def test_link_unknown_barcode_to_existing_product(client):
    # Create product first
    create_r = await client.post("/api/v1/catalogue/products", json={
        "sku": "LINK-001", "name": "Link Target", "unit_of_measure": "EA"
    })
    product_id = create_r.json()["data"]["id"]

    link_r = await client.post("/api/v1/catalogue/barcodes/link", json={
        "unlinked_code": "UNKNOWN-CODE-999",
        "code_type": "QR",
        "existing_product_id": product_id,
    })
    assert link_r.status_code == 201
    assert link_r.json()["data"]["code"] == "UNKNOWN-CODE-999"


@pytest.mark.asyncio
async def test_link_unknown_barcode_creates_new_product(client):
    link_r = await client.post("/api/v1/catalogue/barcodes/link", json={
        "unlinked_code": "NEW-CODE-888",
        "code_type": "QR",
        "new_product": {
            "sku": "NEW-FROM-LINK",
            "name": "Brand New Product",
            "unit_of_measure": "EA",
        },
    })
    assert link_r.status_code == 201
