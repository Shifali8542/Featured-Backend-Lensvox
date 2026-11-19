"""
Unit tests for GR business-rule validators.
Pure functions – no database or HTTP required.
"""

import pytest
from datetime import date, timedelta, datetime, timezone

from app.modules.goods_receipt.models import DiscrepancyType
from app.modules.goods_receipt.validators import (
    NEAR_EXPIRY_THRESHOLD_DAYS,
    run_all_validators,
    validate_expiry,
    validate_product_match,
    validate_quantity,
)


class TestQuantityValidation:
    def test_no_flag_when_exact_match(self):
        flags = validate_quantity(100.0, 100.0)
        assert flags == []

    def test_shortage_flagged(self):
        flags = validate_quantity(80.0, 100.0)
        assert len(flags) == 1
        assert flags[0].discrepancy_type == DiscrepancyType.SHORTAGE
        assert "20" in flags[0].description

    def test_excess_flagged(self):
        flags = validate_quantity(120.0, 100.0)
        assert len(flags) == 1
        assert flags[0].discrepancy_type == DiscrepancyType.EXCESS

    def test_zero_received_is_full_shortage(self):
        flags = validate_quantity(0.0, 100.0)
        assert flags[0].discrepancy_type == DiscrepancyType.SHORTAGE


class TestExpiryValidation:
    def _today(self):
        return datetime.now(tz=timezone.utc).date()

    def test_no_flag_for_none_expiry(self):
        assert validate_expiry(None) == []

    def test_expired_product_flagged(self):
        yesterday = self._today() - timedelta(days=1)
        flags = validate_expiry(yesterday)
        assert flags[0].discrepancy_type == DiscrepancyType.EXPIRED

    def test_near_expiry_flagged(self):
        soon = self._today() + timedelta(days=NEAR_EXPIRY_THRESHOLD_DAYS - 1)
        flags = validate_expiry(soon)
        assert flags[0].discrepancy_type == DiscrepancyType.NEAR_EXPIRY

    def test_no_flag_for_distant_expiry(self):
        far = self._today() + timedelta(days=NEAR_EXPIRY_THRESHOLD_DAYS + 10)
        assert validate_expiry(far) == []


class TestProductMatchValidation:
    def test_no_flag_when_ids_match(self):
        assert validate_product_match("abc", "abc") == []

    def test_mismatch_flagged(self):
        flags = validate_product_match("aaa", "bbb")
        assert flags[0].discrepancy_type == DiscrepancyType.WRONG_PRODUCT

    def test_no_flag_when_either_none(self):
        assert validate_product_match(None, "bbb") == []
        assert validate_product_match("aaa", None) == []


class TestRunAllValidators:
    def _today(self):
        return datetime.now(tz=timezone.utc).date()

    def test_clean_receipt_no_flags(self):
        flags = run_all_validators(
            quantity_received=100.0,
            quantity_outstanding=100.0,
            expiry_date=self._today() + timedelta(days=200),
            scanned_product_id="abc",
            po_product_id="abc",
        )
        assert flags == []

    def test_multiple_flags_aggregated(self):
        flags = run_all_validators(
            quantity_received=50.0,
            quantity_outstanding=100.0,
            expiry_date=self._today() - timedelta(days=1),  # expired
            scanned_product_id="abc",
            po_product_id="abc",
        )
        types = {f.discrepancy_type for f in flags}
        assert DiscrepancyType.SHORTAGE in types
        assert DiscrepancyType.EXPIRED in types

    def test_no_outstanding_skips_quantity_check(self):
        flags = run_all_validators(
            quantity_received=50.0,
            quantity_outstanding=None,
            expiry_date=None,
            scanned_product_id=None,
            po_product_id=None,
        )
        assert flags == []
