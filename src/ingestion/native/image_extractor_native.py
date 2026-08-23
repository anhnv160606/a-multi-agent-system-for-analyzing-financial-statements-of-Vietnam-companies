"""
Image Extractor for Native PDF Documents.
Extracts embedded images & charts from PDF streams, filters out icons/logos,
and stores high-value visuals in data/processed/images/.
"""

from pathlib import Path
from typing import List, Optional

import fitz

try:
    from src.ingestion.models import ExtractedImage
except ImportError:
    from src.ingestion.common.models import ExtractedImage

from src.utils.logger import get_logger

logger = get_logger("src.ingestion.native.image_extractor")


class ImageExtractorNative:
    """
    Extracts high-resolution images & charts from native PDF files using PyMuPDF.
    """

    def __init__(
        self,
        min_width: int = 150,
        min_height: int = 150,
        min_area: int = 25000,
        output_dir: Optional[str | Path] = None,
    ):
        self.min_width = min_width
        self.min_height = min_height
        self.min_area = min_area

        if output_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.output_dir = project_root / "data" / "processed" / "images"
        else:
            self.output_dir = Path(output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_images_from_pdf(self, pdf_path: str | Path) -> List[ExtractedImage]:
        """
        Extracts candidate charts and images from a native PDF document.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        extracted_images: List[ExtractedImage] = []
        pdf_stem = pdf_path.stem
        doc_image_dir = self.output_dir / pdf_stem
        doc_image_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        logger.info(f"Extracting native images from: {pdf_path.name}")

        try:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                image_list = page.get_images(full=True)

                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image.get("image")
                    image_ext = base_image.get("ext", "png")
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter out small graphics, borders, icons
                    if not self._is_meaningful_image(width, height):
                        continue

                    # Save image file
                    img_filename = f"page_{page_num}_img_{img_idx + 1}.{image_ext}"
                    img_path = doc_image_dir / img_filename
                    with open(img_path, "wb") as f:
                        f.write(image_bytes)

                    # Initial heuristic classification
                    aspect_ratio = width / max(height, 1)
                    img_type = "chart" if (1.0 <= aspect_ratio <= 3.0 and width >= 300) else "general"

                    extracted = ExtractedImage(
                        page_num=page_num,
                        image_index=img_idx + 1,
                        file_path=str(img_path),
                        image_bytes=image_bytes,
                        width=width,
                        height=height,
                        ext=image_ext,
                        bbox=None,
                        image_type=img_type,
                        extraction_engine="fitz",
                    )
                    extracted_images.append(extracted)

        except Exception as e:
            logger.error(f"Error during native image extraction for {pdf_path.name}: {e}")
        finally:
            doc.close()

        logger.info(f"Extracted {len(extracted_images)} images from {pdf_path.name}")
        return extracted_images

    def _is_meaningful_image(self, width: int, height: int) -> bool:
        """Checks whether image dimensions qualify as a chart or analytical diagram."""
        if width < self.min_width or height < self.min_height:
            return False
        if (width * height) < self.min_area:
            return False
        aspect_ratio = width / max(height, 1)
        if aspect_ratio > 10.0 or aspect_ratio < 0.1:
            return False
        return True
