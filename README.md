# Goods Receipt IMS – Backend

Python / FastAPI backend for the **Goods Receipt** feature of the Inventory Management System (IMS).

---

## Architecture Overview

```
goods_receipt_backend/
├── app/
│   ├── api/v1/           ← versioned router aggregator
│   ├── core/             ← config, logging, security
│   ├── database/         ← async SQLAlchemy engine + session
│   ├── exceptions/       ← exception hierarchy + handlers
│   ├── utils/            ← response helpers
│   └── modules/
│       ├── label_parser/ ← 6-case label engine (Cases A–F)
│       ├── catalogue/    ← products + label code registry
│       ├── purchase_order/ ← PO CRUD + matching logic
│       ├── goods_receipt/  ← GR workflow, validators, discrepancies
│       └── inventory/    ← stock levels + movement audit log
├── tests/
│   ├── unit/             ← pure-function tests (no DB)
│   └── integration/      ← HTTP tests via in-memory SQLite
├── migrations/           ← Alembic async migrations
├── .env.example
├── requirements.txt
└── run.py
```

### Label Cases Supported

| Case | Label type | Description |
|------|-----------|-------------|
| A | GS1 | Structured GS1 barcode / QR with Application Identifiers (GTIN, batch, expiry …) |
| B | Plain barcode | EAN-13, UPC-A, Code-128 – product looked up by barcode in catalogue |
| C | Supplier QR | Proprietary JSON or key=value QR format |
| D | Manual | No barcode – employee searches by product name or SKU |
| E | Damaged | Employee types the printed digits; fallback to manual search |
| F | Unknown | Unlinked barcode – authorised catalogue user links it or creates a product |

---

## Local Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (for production; tests use in-memory SQLite)

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd goods_receipt_backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt --break-system-packages
# or inside a venv (no flag needed):
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env – set DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY
```

Minimum required `.env` values:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/goods_receipt_db
SECRET_KEY=change-me
JWT_SECRET_KEY=change-me-jwt
```

### 4. Create the database

```bash
# Using psql
psql -U postgres -c "CREATE DATABASE goods_receipt_db;"
```

### 5. Run migrations

```bash
# Generate first migration (auto-detect models)
alembic -c migrations/alembic.ini revision --autogenerate -m "initial schema"

# Apply migrations
alembic -c migrations/alembic.ini upgrade head
```

### 6. Start the server

```bash
python run.py
# or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Open Swagger documentation

```
http://localhost:8000/docs
```

ReDoc alternative:
```
http://localhost:8000/redoc
```

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only (no DB required)
pytest tests/unit/ -v

# Integration tests (uses in-memory SQLite)
pytest tests/integration/ -v

# With coverage report
pytest --cov=app --cov-report=term-missing
```

---

## API Endpoints

### Label Parser

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/labels/scan` | Scan or manually enter a label (Cases A–F) |
| GET | `/api/v1/labels/types` | List supported label types |

### Catalogue

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/catalogue/products` | Create a product |
| GET | `/api/v1/catalogue/products` | Search products by SKU or name |
| GET | `/api/v1/catalogue/products/{id}` | Get product by ID |
| PATCH | `/api/v1/catalogue/products/{id}` | Update product |
| POST | `/api/v1/catalogue/products/{id}/codes` | Add a barcode to a product |
| POST | `/api/v1/catalogue/barcodes/link` | Case F: link unknown barcode |

### Purchase Orders

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/purchase-orders` | Create PO with lines |
| GET | `/api/v1/purchase-orders` | List open POs |
| GET | `/api/v1/purchase-orders/{id}` | Get PO detail |
| PATCH | `/api/v1/purchase-orders/{id}/status` | Update PO status |

### Goods Receipts

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/goods-receipts` | Create GR and process all scanned lines |
| GET | `/api/v1/goods-receipts/{id}` | Get GR detail |
| POST | `/api/v1/goods-receipts/{id}/lines` | Add a single scanned line |
| POST | `/api/v1/goods-receipts/{id}/finalise` | Finalise + update inventory |
| GET | `/api/v1/goods-receipts/{id}/summary` | Get discrepancy summary |

### Inventory

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/inventory/products/{id}` | Get stock levels |
| GET | `/api/v1/inventory/products/{id}/movements` | Audit trail |
| POST | `/api/v1/inventory/adjust` | Manual stock adjustment |

---

## Sample Requests

### Case A – GS1 Barcode

```json
POST /api/v1/labels/scan
{
  "raw_data": "0101234567890128171231101BATCH-XYZ",
  "label_type_hint": "GS1"
}
```

### Case D – Manual Entry

```json
POST /api/v1/labels/scan
{
  "label_type_hint": "MANUAL",
  "manual_product_ref": "PROD-00123",
  "manual_batch": "BATCH-2024-001",
  "manual_expiry": "2025-12-31"
}
```

### Case F – Link Unknown Barcode

```json
POST /api/v1/catalogue/barcodes/link
{
  "unlinked_code": "UNKNOWN-BARCODE-999",
  "code_type": "QR",
  "existing_product_id": "00000000-0000-0000-0000-000000000001"
}
```

### Create Goods Receipt

```json
POST /api/v1/goods-receipts
{
  "purchase_order_id": "00000000-0000-0000-0000-000000000002",
  "lines": [
    {
      "parsed_label": { ... },
      "quantity_received": 100.0,
      "unit_of_measure": "EA"
    }
  ]
}
```

---

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Async Postgres URL | required |
| `SECRET_KEY` | App secret | required |
| `JWT_SECRET_KEY` | JWT signing key | required |
| `JWT_ALGORITHM` | JWT algorithm | HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | 60 |
| `DEBUG` | Debug mode | false |
| `ENVIRONMENT` | development \| production | development |
| `LOG_LEVEL` | Logging level | INFO |
| `LOG_FORMAT` | json \| text | json |
