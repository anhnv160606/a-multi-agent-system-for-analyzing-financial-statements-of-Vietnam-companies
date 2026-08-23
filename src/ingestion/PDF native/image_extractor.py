"""
PDF Image Extraction Module (Task 1.5).
Extracts embedded images from PDF pages, filters out small decorative icons/logos,
and saves high-value charts/diagrams for downstream Vision LLM processing.
"""

from pathlib import Path
from typing import List, Optional

from src.ingestion.models import ExtractedImage
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.image_extractor")


class ImageExtractor:
    """
    Extracts high-resolution images & charts from PDF files using PyMuPDF.
    Filters out decorative icons, signatures, and small logos automatically.
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
            project_root = Path(__file__).resolve().parent.parent.parent
            self.output_dir = project_root / "data" / "processed" / "images"
        else:
            self.output_dir = Path(output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_images_from_pdf(self, pdf_path: str | Path) -> List[ExtractedImage]:
        """
        Extracts all candidate chart/diagram images from a PDF file.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        extracted_images: List[ExtractedImage] = []
        pdf_stem = pdf_path.stem
        doc_image_dir = self.output_dir / pdf_stem
        doc_image_dir.mkdir(parents=True, exist_ok=True)

        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF (fitz) is required for image extraction.")
            return []

        doc = fitz.open(str(pdf_path))
        logger.info(f"Extracting images from: {pdf_path.name}")

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

                    # Filter out small icons, bullet points, headers
                    if not self._is_meaningful_image(width, height):
                        continue

                    # Determine file path and save
                    img_filename = f"page_{page_num}_img_{img_idx + 1}.{image_ext}"
                    img_path = doc_image_dir / img_filename
                    with open(img_path, "wb") as f:
                        f.write(image_bytes)

                    # Classify initial image type
                    img_type = self._classify_candidate_type(width, height)

                    extracted = ExtractedImage(
                        page_num=page_num,
                        image_index=img_idx + 1,
                        image_path=str(img_path),
                        image_bytes=image_bytes,
                        width=width,
                        height=height,
                        format=image_ext,
                        bbox=None,
                        image_type=img_type,
                    )
                    extracted_images.append(extracted)

        except Exception as e:
            logger.error(f"Error during image extraction for {pdf_path.name}: {e}")
        finally:
            doc.close()

        logger.info(
            f"Extracted {len(extracted_images)} candidate images from {pdf_path.name} (saved to {doc_image_dir})"
        )
        return extracted_images

    def _is_meaningful_image(self, width: int, height: int) -> bool:
        """Determines if the image is large enough to contain charts or analytical diagrams."""
        if width < self.min_width or height < self.min_height:
            return False
        if (width * height) < self.min_area:
            return False
        # Avoid extreme 1-dimensional stripes (decorative bars)
        aspect_ratio = width / max(height, 1)
        if aspect_ratio > 10.0 or aspect_ratio < 0.1:
            return False
        return True

    def _classify_candidate_type(self, width: int, height: int) -> str:
        """Initial heuristic classification for extracted images."""
        aspect_ratio = width / max(height, 1)
        # Charts are commonly horizontal rectangles or square
        if 1.0 <= aspect_ratio <= 3.0 and width >= 300:
            return "chart"
        return "general"
