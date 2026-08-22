"""
Image & Chart Processing Module (Task 1.6).
Transcribes financial charts to structured Markdown tables (Chart-to-Data)
and generates descriptive captions using Google Gemini Vision (100% Free Tier).
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml

from src.ingestion.models import ExtractedImage, ImageProcessingResult
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.image_processor")


class ImageProcessor:
    """
    Processes financial charts and diagrams extracted from PDFs.
    Uses Google Gemini Vision API (Free Tier) with offline fallback.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name
        self.prompt_config = self._load_prompt_template()
        self._genai_client = None
        self._init_vision_client()

    def _load_prompt_template(self) -> dict:
        """Loads prompt template from prompts/image_captioner.yaml."""
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent
            / "prompts"
            / "image_captioner.yaml"
        )
        if prompt_path.exists():
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.warning(f"Failed to load image captioner prompt: {e}")
        return {
            "system_prompt": "Bạn là chuyên gia phân tích tài chính. Hãy trích xuất dữ liệu từ biểu đồ này thành bảng Markdown.",
            "user_template": "Phân tích biểu đồ và trích xuất bảng số liệu.",
        }

    def _init_vision_client(self):
        """Initializes Google GenAI vision client if API key is provided."""
        if not self.api_key:
            logger.info("No GOOGLE_API_KEY found. ImageProcessor will operate in offline/fallback mode.")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai_client = genai.GenerativeModel(self.model_name)
            logger.info(f"Initialized Google Gemini Vision model: {self.model_name}")
        except Exception as e:
            logger.warning(f"Could not initialize Google GenAI Vision client: {e}")
            self._genai_client = None

    def process_image(self, extracted_image: ExtractedImage) -> ImageProcessingResult:
        """
        Processes a single extracted image, returning captions and chart data.
        """
        # If Gemini Vision client is available and image path exists, call API
        if self._genai_client and extracted_image.image_path and Path(extracted_image.image_path).exists():
            try:
                import google.generativeai as genai
                from PIL import Image

                img = Image.open(extracted_image.image_path)
                prompt = (
                    f"{self.prompt_config.get('system_prompt', '')}\n\n"
                    f"Trang tài liệu: {extracted_image.page_num}. "
                    "Hãy phân tích biểu đồ/hình ảnh này, trích xuất dữ liệu số thành bảng Markdown nếu có."
                )

                response = self._genai_client.generate_content([prompt, img])
                text_result = response.text if response else ""

                # Extract markdown chart if enclosed in markdown table
                chart_data = self._extract_markdown_from_response(text_result)
                image_type = "chart" if chart_data else extracted_image.image_type

                return ImageProcessingResult(
                    image_index=extracted_image.image_index,
                    page_num=extracted_image.page_num,
                    caption=text_result[:500],
                    chart_data=chart_data,
                    image_type=image_type,
                    confidence=0.95,
                )
            except Exception as e:
                logger.warning(f"Gemini Vision call failed for image on page {extracted_image.page_num}: {e}")

        # Fallback offline processing
        return self._offline_process(extracted_image)

    def process_batch(self, images: List[ExtractedImage]) -> List[ImageProcessingResult]:
        """Processes a batch of extracted images."""
        results = []
        for img in images:
            results.append(self.process_image(img))
        return results

    def _offline_process(self, image: ExtractedImage) -> ImageProcessingResult:
        """Heuristic offline caption generator when Vision API is not active."""
        caption = (
            f"Hình ảnh {image.image_type} (Kích thước {image.width}x{image.height}px) "
            f"được trích xuất từ trang {image.page_num} của báo cáo tài chính."
        )
        return ImageProcessingResult(
            image_index=image.image_index,
            page_num=image.page_num,
            caption=caption,
            chart_data=None,
            image_type=image.image_type,
            confidence=0.8,
        )

    def _extract_markdown_from_response(self, text: str) -> Optional[str]:
        """Extracts markdown table block from LLM response text."""
        lines = text.split("\n")
        table_lines = [l for l in lines if "|" in l]
        if len(table_lines) >= 3:
            return "\n".join(table_lines)
        return None
