"""
Unit tests for the GS1 Application Identifier parser.
No database required.
"""

import pytest
from datetime import date

from app.modules.label_parser.gs1_parser import (
    extract_label_fields,
    parse_gs1,
    _parse_gs1_date,
)


class TestGS1DateParsing:
    def test_simple_date_20xx(self):
        assert _parse_gs1_date("251231") == date(2025, 12, 31)

    def test_simple_date_19xx(self):
        assert _parse_gs1_date("991231") == date(1999, 12, 31)

    def test_day_zero_becomes_last_of_month(self):
        d = _parse_gs1_date("250200")
        assert d == date(2025, 2, 28)

    def test_invalid_date_returns_none(self):
        assert _parse_gs1_date("XXXXXX") is None

    def test_wrong_length_returns_none(self):
        assert _parse_gs1_date("2501") is None


class TestGS1Parser:
    def test_gtin_only(self):
        # AI 01 = GTIN (14 digits)
        raw = "0100614141000415"
        result = parse_gs1(raw)
        assert result["01"] == "00614141000415"

    def test_gtin_batch_expiry(self):
        # AI 01 GTIN + AI 17 expiry + AI 10 batch
        raw = "010061414100041517251231" + chr(29) + "10BATCH001"
        result = parse_gs1(raw)
        assert result["01"] == "00614141000415"
        assert result["17"] == "251231"
        assert result["10"] == "BATCH001"

    def test_extract_fields_produces_semantic_dict(self):
        raw = "010061414100041517251231" + chr(29) + "10LOT-XYZ"
        fields = extract_label_fields(raw)
        assert fields["gtin"] == "00614141000415"
        assert fields["expiry_date"] == date(2025, 12, 31)
        assert fields["batch_number"] == "LOT-XYZ"

    def test_non_gs1_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_gs1("NOTAGS")

    def test_short_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_gs1("01")


class TestGS1LooksLike:
    def test_known_prefix_accepted(self):
        from app.modules.label_parser.gs1_parser import _looks_like_gs1
        assert _looks_like_gs1("0112345") is True

    def test_random_alpha_rejected(self):
        from app.modules.label_parser.gs1_parser import _looks_like_gs1
        assert _looks_like_gs1("ABCDEF") is False
