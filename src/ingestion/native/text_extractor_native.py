"""
Text Extractor for Native PDF Documents.
Extracts pure narrative text, headings, and notes while strictly excluding table and image areas.
"""

from pathlib import Path
from typing import List, Optional

import fitz

try:
    from src.ingestion.models import PageContent
except ImportError:
    from src.ingestion.models import PageContent

from src.ingestion.native.pdf_layout import PDFLayoutDetector
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.native.text_extractor")


class TextExtractorNative:
    """
    Extracts structured narrative text from native PDFs without table contamination.
    """

    def __init__(self, layout_detector: Optional[PDFLayoutDetector] = None):
        self.layout_detector = layout_detector or PDFLayoutDetector()

    def extract_text_from_pdf(self, pdf_path: str | Path) -> List[PageContent]:
        """
        Extracts pure text from all pages of a native PDF document.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        pages_content: List[PageContent] = []
        doc = fitz.open(str(pdf_path))
        logger.info(f"Extracting native text from: {pdf_path.name}")

        try:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1

                # 1. Analyze layout to find pure text blocks outside tables/images
                layout = self.layout_detector.analyze_page(page, page_num)

                # 2. Sort text blocks top-to-bottom, left-to-right
                sorted_blocks = sorted(
                    layout.text_blocks,
                    key=lambda b: (round(b["bbox"][1] / 10.0) * 10.0, b["bbox"][0])
                )

                # 3. Assemble cleaned text paragraphs
                paragraphs = [b["text"] for b in sorted_blocks if b.get("text")]
                page_narrative_text = "\n\n".join(paragraphs).strip()

                pages_content.append(
                    PageContent(
                        page_num=page_num,
                        text=page_narrative_text,
                        extraction_engine="fitz",
                        layout_info={
                            "num_text_blocks": len(sorted_blocks),
                            "num_tables_excluded": len(layout.table_bboxes),
                            "num_images_excluded": len(layout.image_bboxes),
                        },
                    )
                )

        finally:
            doc.close()

        logger.info(f"Extracted pure text from {len(pages_content)} pages in {pdf_path.name}")
        return pages_content
