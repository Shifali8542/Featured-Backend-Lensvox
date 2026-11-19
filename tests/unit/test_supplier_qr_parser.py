"""
Unit tests for the supplier QR parser (Case C).
No database required.
"""

import pytest
from datetime import date

from app.modules.label_parser.supplier_qr_parser import (
    CsvStyleSupplierParser,
    GenericJsonSupplierParser,
    parse_supplier_qr,
)


class TestGenericJsonSupplierParser:
    def setup_method(self):
        self.parser = GenericJsonSupplierParser()

    def test_can_handle_json(self):
        assert self.parser.can_handle('{"sku": "ABC"}') is True

    def test_cannot_handle_plain_barcode(self):
        assert self.parser.can_handle("5901234123457") is False

    def test_parses_sku_and_batch(self):
        raw = '{"sku":"PROD-999","batch":"L44","exp":"2025-06-30"}'
        result = self.parser.parse(raw)
        assert result["sku"] == "PROD-999"
        assert result["batch_number"] == "L44"
        assert result["expiry_date"] == date(2025, 6, 30)

    def test_parses_quantity(self):
        raw = '{"sku":"X","qty":10}'
        result = self.parser.parse(raw)
        assert result["quantity"] == 10.0

    def test_unknown_keys_ignored(self):
        raw = '{"sku":"X","weird_field":"y"}'
        result = self.parser.parse(raw)
        assert "weird_field" not in result


class TestCsvStyleSupplierParser:
    def setup_method(self):
        self.parser = CsvStyleSupplierParser()

    def test_can_handle_pipe_format(self):
        assert self.parser.can_handle("SKU=PROD001|BATCH=B22|EXP=2025-06-01") is True

    def test_cannot_handle_json(self):
        assert self.parser.can_handle('{"key":"val"}') is False

    def test_parses_pipe_delimited(self):
        raw = "SKU=PROD001|BATCH=B22|EXP=2025-06-01"
        result = self.parser.parse(raw)
        assert result["sku"] == "PROD001"
        assert result["batch_number"] == "B22"
        assert result["expiry_date"] == date(2025, 6, 1)

    def test_parses_semicolon_delimited(self):
        raw = "SKU=X;BATCH=YY"
        result = self.parser.parse(raw)
        assert result["sku"] == "X"
        assert result["batch_number"] == "YY"


class TestParseSupplierQr:
    def test_dispatches_json(self):
        raw = '{"sku":"A","batch":"B1","exp":"2026-01-01"}'
        result = parse_supplier_qr(raw)
        assert result is not None
        assert result["sku"] == "A"

    def test_dispatches_csv(self):
        raw = "SKU=P1|BATCH=L1"
        result = parse_supplier_qr(raw)
        assert result is not None

    def test_returns_none_for_unrecognised(self):
        result = parse_supplier_qr("SOME RANDOM TEXT WITHOUT STRUCTURE")
        assert result is None
