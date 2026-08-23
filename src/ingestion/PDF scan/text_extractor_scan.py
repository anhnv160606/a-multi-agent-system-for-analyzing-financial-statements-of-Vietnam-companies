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


    

