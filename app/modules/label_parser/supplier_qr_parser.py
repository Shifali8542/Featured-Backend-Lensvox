"""
Supplier-specific QR code parser – Case C.

Suppliers often use their own proprietary QR format.
This module uses a registry of supplier-specific parsers identified by
heuristics (key patterns in the payload). New suppliers can be added
by implementing the `SupplierParser` protocol and registering it.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Protocol


class SupplierParser(Protocol):
    def can_handle(self, raw: str) -> bool: ...
    def parse(self, raw: str) -> dict[str, Any]: ...


# ── Generic JSON-based supplier QR ───────────────────────────────────────────

class GenericJsonSupplierParser:
    """
    Handles suppliers that encode data as JSON.
    Tries to map common key names to canonical fields.
    """

    # Mapping of supplier-side key variants → canonical field name
    _KEY_MAP = {
        "gtin": "gtin",
        "sku": "sku",
        "product_code": "sku",
        "item_no": "sku",
        "batch": "batch_number",
        "batch_no": "batch_number",
        "batch_number": "batch_number",
        "lot": "batch_number",
        "lot_no": "batch_number",
        "exp": "expiry_date",
        "expiry": "expiry_date",
        "expiry_date": "expiry_date",
        "exp_date": "expiry_date",
        "best_before": "expiry_date",
        "qty": "quantity",
        "quantity": "quantity",
        "serial": "serial_number",
        "serial_no": "serial_number",
        "serial_number": "serial_number",
        "product_name": "product_name",
        "name": "product_name",
        "description": "product_name",
    }

    def can_handle(self, raw: str) -> bool:
        stripped = raw.strip()
        return stripped.startswith("{") and stripped.endswith("}")

    def parse(self, raw: str) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(raw)
        out: dict[str, Any] = {}
        for k, v in payload.items():
            canonical = self._KEY_MAP.get(k.lower().strip())
            if canonical:
                out[canonical] = _coerce_value(canonical, v)
        return out


# ── CSV-style supplier QR (key=value|key=value) ───────────────────────────────

class CsvStyleSupplierParser:
    """
    Handles pipe- or semicolon-delimited key=value pairs.
    E.g. ``SKU=PROD001|BATCH=B22|EXP=2025-06``
    """

    _RE = re.compile(r"^\w+=\S+([|;]\w+=\S*)*$")

    def can_handle(self, raw: str) -> bool:
        return bool(self._RE.match(raw.strip()))

    def parse(self, raw: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for segment in re.split(r"[|;]", raw):
            if "=" not in segment:
                continue
            k, _, v = segment.partition("=")
            canonical = GenericJsonSupplierParser._KEY_MAP.get(k.lower().strip())
            if canonical:
                out[canonical] = _coerce_value(canonical, v.strip())
        return out


# ── Registry ─────────────────────────────────────────────────────────────────

_PARSERS: list[SupplierParser] = [
    GenericJsonSupplierParser(),
    CsvStyleSupplierParser(),
]


def parse_supplier_qr(raw: str) -> dict[str, Any] | None:
    """
    Try each registered supplier parser in order.
    Returns parsed fields dict, or None if no parser matches.
    """
    for parser in _PARSERS:
        if parser.can_handle(raw):
            return parser.parse(raw)
    return None


# ── Coercion helpers ──────────────────────────────────────────────────────────

def _coerce_value(field: str, value: Any) -> Any:
    if field == "expiry_date":
        return _parse_date(str(value))
    if field == "quantity":
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    return value


def _parse_date(s: str) -> date | None:
    """Try common date formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d", "%Y-%m", "%m/%Y"):
        try:
            from datetime import datetime
            if fmt in ("%Y-%m", "%m/%Y"):
                import calendar
                dt = datetime.strptime(s, fmt)
                last = calendar.monthrange(dt.year, dt.month)[1]
                return date(dt.year, dt.month, last)
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
