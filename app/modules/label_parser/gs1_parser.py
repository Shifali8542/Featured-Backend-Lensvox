"""
GS1 Application Identifier (AI) parser – Case A.

GS1 barcodes / QR codes encode data as a stream of  (AI)(value) segments.
Common AIs used in IMS / pharmaceutical / FMCG contexts:

  01 – GTIN (14 digits)
  10 – Batch/Lot number
  11 – Production date  YYMMDD
  17 – Expiry date      YYMMDD
  21 – Serial number
  30 – Count
  310n – Net weight (n decimal places)
  37 – Quantity

Reference: https://www.gs1.org/standards/barcodes/application-identifiers
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Map AI → (description, fixed_length | None, variable_length_delimiter)
# fixed_length: exact characters to consume; None means variable (up to FNC1 or end)
_AI_SPECS: dict[str, tuple[str, int | None]] = {
    "00": ("SSCC", 18),
    "01": ("GTIN", 14),
    "02": ("CONTENT", 14),
    "10": ("BATCH_LOT", None),
    "11": ("PROD_DATE", 6),
    "13": ("PACK_DATE", 6),
    "15": ("BEST_BEFORE", 6),
    "17": ("EXPIRY_DATE", 6),
    "20": ("VARIANT", 2),
    "21": ("SERIAL", None),
    "22": ("CPV", None),
    "30": ("VAR_COUNT", None),
    "37": ("COUNT", None),
    "310": ("NET_WEIGHT_KG", 6),   # 310n – n from 4th digit
    "320": ("NET_WEIGHT_LB", 6),
    "400": ("ORDER_NUMBER", None),
    "710": ("NHRN_GS1", None),
    "711": ("NHRN_NHPID", None),
}

# Variable-length AIs (data terminated by FNC1 = ASCII 29, or end of string)
_VARIABLE_LENGTH_AIS = {ai for ai, (_, length) in _AI_SPECS.items() if length is None}

_FNC1 = chr(29)  # Group Separator in GS1-128 / GS1 DataMatrix / GS1 QR


def parse_gs1(raw: str) -> dict[str, Any]:
    """
    Parse a GS1-encoded string and return a dict mapping AI → value.
    Handles both compact (no separators) and FNC1-delimited encodings.
    Raises ValueError if `raw` does not look like a GS1 string.
    """
    # Normalise – strip whitespace, replace visible FNC1 representations
    raw = raw.strip().replace("\\x1d", _FNC1).replace(chr(0x1D), _FNC1)

    if not _looks_like_gs1(raw):
        raise ValueError(f"Does not appear to be a GS1-encoded string: {raw!r}")

    result: dict[str, Any] = {}
    pos = 0

    while pos < len(raw):
        if raw[pos] == _FNC1:
            pos += 1
            continue

        ai, ai_len = _match_ai(raw, pos)
        if ai is None:
            logger.debug("GS1 parser: unknown AI at position %d in %r", pos, raw)
            break

        pos += ai_len
        _, fixed_len = _AI_SPECS[ai]

        if fixed_len is not None:
            value = raw[pos: pos + fixed_len]
            pos += fixed_len
        else:
            # Variable length – read until FNC1 or end
            end = raw.find(_FNC1, pos)
            value = raw[pos: end] if end != -1 else raw[pos:]
            pos = end + 1 if end != -1 else len(raw)

        result[ai] = value

    return result


def extract_label_fields(raw: str) -> dict[str, Any]:
    """
    High-level extraction: parse GS1 AIs and return semantically named fields.
    """
    ais = parse_gs1(raw)
    out: dict[str, Any] = {"gs1_ais": ais}

    if "01" in ais:
        out["gtin"] = ais["01"]
    if "10" in ais:
        out["batch_number"] = ais["10"]
    if "21" in ais:
        out["serial_number"] = ais["21"]
    if "17" in ais:
        out["expiry_date"] = _parse_gs1_date(ais["17"])
    if "11" in ais:
        out["manufacture_date"] = _parse_gs1_date(ais["11"])
    if "15" in ais:
        out["expiry_date"] = out.get("expiry_date") or _parse_gs1_date(ais["15"])
    if "37" in ais or "30" in ais:
        qty_str = ais.get("37") or ais.get("30", "")
        try:
            out["quantity"] = float(qty_str)
        except ValueError:
            pass

    return out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _looks_like_gs1(raw: str) -> bool:
    """Heuristic: starts with a known 2-digit AI and is mostly numeric/alphanum."""
    if len(raw) < 4:
        return False
    return raw[:2] in _AI_SPECS or raw[:3] in _AI_SPECS


def _match_ai(raw: str, pos: int) -> tuple[str | None, int]:
    """Try matching 3-char then 2-char AI at `pos`. Returns (ai, ai_len)."""
    for ai_len in (3, 2):
        candidate = raw[pos: pos + ai_len]
        if candidate in _AI_SPECS:
            return candidate, ai_len
    return None, 0


def _parse_gs1_date(yymmdd: str) -> date | None:
    """
    Convert GS1 date YYMMDD → Python date.
    Year < 50 → 20xx; year >= 50 → 19xx (GS1 spec).
    DD = 00 means last day of the month.
    """
    if len(yymmdd) != 6:
        return None
    try:
        yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
        year = 2000 + yy if yy < 50 else 1900 + yy
        if dd == 0:
            import calendar
            dd = calendar.monthrange(year, mm)[1]
        return date(year, mm, dd)
    except (ValueError, OverflowError):
        return None
