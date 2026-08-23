"""
PDF Layout Analysis & Region Segmentation Module (Native PDF).
Detects table, image, and text bounding boxes per page to prevent duplicate content extraction.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from src.utils.logger import get_logger

logger = get_logger("src.ingestion.native.pdf_layout")

# Bounding box type: (x0, y0, x1, y1)
BBox = Tuple[float, float, float, float]


@dataclass
class PageLayout:
    """Represents the segmented spatial layout of a single PDF page."""
    page_num: int
    width: float
    height: float
    table_bboxes: List[BBox] = field(default_factory=list)
    image_bboxes: List[BBox] = field(default_factory=list)
    text_blocks: List[Dict[str, Any]] = field(default_factory=list)


class PDFLayoutDetector:
    """
    Spatial layout detector for native PDF pages.
    Extracts table boundaries, image regions, and filters non-table text blocks.
    """

    def __init__(self, min_image_size: int = 80, overlap_threshold: float = 0.25):
        self.min_image_size = min_image_size
        self.overlap_threshold = overlap_threshold

    def analyze_page(self, page: fitz.Page, page_num: int) -> PageLayout:
        """
        Analyzes a single PyMuPDF page and returns structured PageLayout.
        """
        rect = page.rect
        width, height = rect.width, rect.height

        # 1. Detect table bounding boxes
        table_bboxes = self._detect_table_bboxes(page)

        # 2. Detect image bounding boxes
        image_bboxes = self._detect_image_bboxes(page)

        # 3. Detect text blocks excluding table and image areas
        exclusion_zones = table_bboxes + image_bboxes
        text_blocks = self._extract_pure_text_blocks(page, exclusion_zones)

        logger.debug(
            f"Page {page_num} layout: {len(table_bboxes)} tables, "
            f"{len(image_bboxes)} images, {len(text_blocks)} pure text blocks."
        )

        return PageLayout(
            page_num=page_num,
            width=width,
            height=height,
            table_bboxes=table_bboxes,
            image_bboxes=image_bboxes,
            text_blocks=text_blocks,
        )

    def _detect_table_bboxes(self, page: fitz.Page) -> List[BBox]:
        """Detects tables using PyMuPDF find_tables feature."""
        table_bboxes: List[BBox] = []
        try:
            tabs = page.find_tables()
            for tab in tabs:
                bbox = tab.bbox  # (x0, y0, x1, y1)
                # Expand slightly to cover outer table borders
                padded_bbox = (
                    max(0.0, bbox[0] - 2.0),
                    max(0.0, bbox[1] - 2.0),
                    min(page.rect.width, bbox[2] + 2.0),
                    min(page.rect.height, bbox[3] + 2.0),
                )
                table_bboxes.append(padded_bbox)
        except Exception as e:
            logger.debug(f"Table detection error on page: {e}")
        return table_bboxes

    def _detect_image_bboxes(self, page: fitz.Page) -> List[BBox]:
        """Detects image rectangles on the page."""
        image_bboxes: List[BBox] = []
        try:
            image_list = page.get_images(full=True)
            for img_info in image_list:
                xref = img_info[0]
                rects = page.get_image_rects(xref)
                for r in rects:
                    if r.width >= self.min_image_size and r.height >= self.min_image_size:
                        image_bboxes.append((r.x0, r.y0, r.x1, r.y1))
        except Exception as e:
            logger.debug(f"Image detection error on page: {e}")
        return image_bboxes

    def _extract_pure_text_blocks(
        self, page: fitz.Page, exclusion_zones: List[BBox]
    ) -> List[Dict[str, Any]]:
        """
        Extracts text blocks and filters out any block overlapping with tables or images.
        """
        raw_blocks = page.get_text("blocks")
        pure_text_blocks: List[Dict[str, Any]] = []

        for block in raw_blocks:
            # block format: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type == 0 indicates text (type 1 indicates image)
            if len(block) < 6:
                continue

            x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
            block_type = block[6] if len(block) > 6 else 0
            if block_type != 0:
                continue

            clean_text = text.strip()
            if not clean_text:
                continue

            block_bbox: BBox = (x0, y0, x1, y1)

            # Check if this text block falls inside any exclusion zone
            if self._is_overlapping_any(block_bbox, exclusion_zones):
                continue

            pure_text_blocks.append({
                "bbox": block_bbox,
                "text": clean_text,
                "lines_count": clean_text.count("\n") + 1,
            })

        return pure_text_blocks

    def _is_overlapping_any(self, box: BBox, exclusion_zones: List[BBox]) -> bool:
        """Calculates area overlap ratio between box and exclusion zones."""
        box_area = max(1.0, (box[2] - box[0]) * (box[3] - box[1]))

        for ex in exclusion_zones:
            # Intersection coordinates
            ix0 = max(box[0], ex[0])
            iy0 = max(box[1], ex[1])
            ix1 = min(box[2], ex[2])
            iy1 = min(box[3], ex[3])

            if ix1 > ix0 and iy1 > iy0:
                intersection_area = (ix1 - ix0) * (iy1 - iy0)
                overlap_ratio = intersection_area / box_area
                if overlap_ratio >= self.overlap_threshold:
                    return True
        return False
