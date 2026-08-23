from typing import List
import cv2
import numpy as np
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from src.utils.logger import get_logger
from src.ingestion.models import PageContent 

logger = get_logger("src.ingestion.scan.text_extractor_scan")

class TextExtractorScan:
    def __init__(self, lang: str="vie", use_paddle: bool=False):
        self.lang = lang
        self.use_paddle = use_paddle
        self._paddle_ocr = None
        if self.use_paddle:
            try:
                from paddleocr import PaddleOCR
                self._paddle_ocr = PaddleOCR(use_angle_cls=True, lang=self.lang)
            except ImportError:
                logger.warning("PaddleOCR is not installed. Falling back to Tesseract OCR.")
                self.use_paddle = False

    def _preprocess_image(self, image: Image.Image) -> np.ndarray:
        """Tiền xử lý ảnh để tăng độ chính xác OCR."""
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        denoised = cv2.medianBlur(gray, 3)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        bitwise_not = cv2.bitwise_not(enhanced)
        coords = np.column_stack(np.where(bitwise_not > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            (h, w) = enhanced.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            deskewed = cv2.warpAffine(
                enhanced, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
        else:
            deskewed = enhanced
 
        return deskewed

    def extract_page(self, image: Image.Image, page_num: int, pdf_path: str=" ") -> PageContent:
        """Trích text thuần từ 1 trang PDF scan (không có bảng)."""
        preprocessed_image = self._preprocess_image(image)
        if self.use_paddle and self._paddle_ocr is not None:
            result = self._paddle_ocr.ocr(preprocessed_image, cls=True)
            text = "\n".join([line[1][0] for line in result[0]]) if result and result[0] else ""
            extraction_engine = "paddleocr"
        else:
            text = pytesseract.image_to_string(preprocessed_image, lang=self.lang)
            extraction_engine = "tesseract"

        return PageContent(
            page_num=page_num,
            text=text.strip(),
            extraction_engine=extraction_engine,
            layout_info={"source": pdf_path},
        ) 

    def extract_text_from_pages( self, pdf_path: str, page_numbers: List[int], dpi: int = 300
) -> List[PageContent]:
        images = convert_from_path(pdf_path, dpi=dpi)
        results = []
        for page_num in page_numbers:
            idx = page_num - 1
            if idx < 0 or idx >= len(images):
                logger.warning(f"Trang {page_num} vượt phạm vi file.")
                continue
            results.append(self.extract_page(images[idx], page_num, pdf_path))
        return results
        
    


    

