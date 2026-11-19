"""
OCR Service — extracts text from product label photos using pytesseract.

Used for labels that have no barcode or QR code, only printed text.
The extracted text is then passed through the normal LabelParserService pipeline.
"""

from __future__ import annotations

import io
import logging
import re

logger = logging.getLogger(__name__)


class OcrService:
    """Wraps pytesseract to extract text from label images."""

    # Tesseract config: single-block of text, optimised for labels
    _TESSERACT_CONFIG = "--psm 6 --oem 3"

    def extract_text(self, image_bytes: bytes) -> str:
        """
        Run OCR on raw image bytes and return cleaned plain text.

        Args:
            image_bytes: Raw bytes of a JPEG or PNG image.

        Returns:
            Extracted text, stripped and normalised. Empty string if nothing found.
        """
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
        except ImportError as exc:
            logger.error("pytesseract or Pillow not installed: %s", exc)
            return ""

        try:
            # Load image from bytes
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

            # Pre-process for better OCR accuracy on warehouse labels
            img = self._preprocess(img)

            # Run OCR
            raw_text: str = pytesseract.image_to_string(
                img,
                config=self._TESSERACT_CONFIG,
            )

            cleaned = self._clean(raw_text)
            logger.info("OCR extracted %d chars", len(cleaned))
            return cleaned

        except Exception as exc:  # noqa: BLE001
            logger.exception("OCR failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(img):
        """
        Enhance contrast and sharpen — helps OCR on printed product labels
        that may be photographed under warehouse lighting.
        """
        from PIL import ImageEnhance, ImageFilter

        # Upscale small images so tesseract has more pixels to work with
        w, h = img.size
        if max(w, h) < 800:
            scale = 800 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)))

        # Sharpen edges
        img = img.filter(ImageFilter.SHARPEN)

        # Boost contrast
        img = ImageEnhance.Contrast(img).enhance(1.8)

        # Boost brightness slightly (labels are often dark photos)
        img = ImageEnhance.Brightness(img).enhance(1.2)

        return img

    @staticmethod
    def _clean(text: str) -> str:
        """
        Remove noise characters common in tesseract output on label photos.
        Preserves alphanumeric content, punctuation, and whitespace.
        """
        if not text:
            return ""

        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove lines that are only punctuation / noise (e.g. "|||", "---")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            # Keep the line if it has at least 2 alphanumeric chars
            if sum(c.isalnum() for c in stripped) >= 2:
                lines.append(stripped)

        return "\n".join(lines).strip()

    def extract_best_identifier(self, image_bytes: bytes) -> str:
        """
        Extract the single best product identifier from a barcode/label photo.

        Strategy:
        1. Try to find a barcode-like string: digits, letters, hyphens, 6-30 chars
        2. Fall back to shortest meaningful line (product code / SKU)
        3. Fall back to full OCR text if nothing short found

        This avoids using the entire box text as a product name.
        """
        full_text = self.extract_text(image_bytes)
        if not full_text:
            return ""

        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        if not lines:
            return ""

        # Pattern: looks like a barcode/serial number
        # e.g. "JM07FF65897802359" or "4901234567890" or "ABC-12345-XY"
        barcode_pattern = re.compile(
            r'^[A-Z0-9][A-Z0-9\-\.\/]{5,29}$', re.IGNORECASE
        )

        # First pass: look for a barcode-like line (short, mostly alphanumeric)
        for line in lines:
            clean = re.sub(r'[^A-Z0-9\-\.\/]', '', line.upper())
            if barcode_pattern.match(clean) and len(clean) >= 6:
                logger.info("OCR best identifier (barcode-like): %s", clean)
                return clean

        # Second pass: shortest line that isn't noise (good for SKU/model number)
        candidates = [l for l in lines if 4 <= len(l) <= 60]
        if candidates:
            best = min(candidates, key=len)
            logger.info("OCR best identifier (shortest line): %s", best)
            return best

        # Fallback: first line of full text
        result = lines[0][:80]
        logger.info("OCR best identifier (first line): %s", result)
        return result