"""Phát hiện NHANH một trang scan có chứa bảng hay không -- dùng để routing
giữa text_extractor_scan.py và table_extractor_scan.py.
"""

from typing import List

import cv2
import numpy as np
from PIL import Image

from src.utils.logger import get_logger

logger = get_logger("src.ingestion.scan.page_type_detector_scan")


class PageTypeDetectorScan:
    def __init__(self, min_horizontal_lines: int = 3, min_vertical_lines: int = 2):
        """
        Args:
            min_horizontal_lines: số đường kẻ ngang tối thiểu để coi là có bảng.
              3 đường kẻ ngang tối thiểu tương ứng với 1 bảng có ít nhất 2 hàng
              dữ liệu (header + 1 hàng + đường kẻ đáy).
            min_vertical_lines: số đường kẻ dọc tối thiểu (2 = ít nhất 1 cột,
              tức 2 đường viền trái/phải).
        """
        self.min_horizontal_lines = min_horizontal_lines
        self.min_vertical_lines = min_vertical_lines

    def page_has_table(self, image: Image.Image) -> bool:
        """True nếu trang có đủ số đường kẻ ngang VÀ dọc để coi là có bảng."""
        gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        # Otsu threshold + đảo ngược màu (đường kẻ/chữ thành pixel trắng
        # trên nền đen) để morphology hoạt động đúng
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h_lines = self._count_lines(binary, orientation="horizontal")
        v_lines = self._count_lines(binary, orientation="vertical")

        return h_lines >= self.min_horizontal_lines and v_lines >= self.min_vertical_lines

    def _count_lines(self, binary: np.ndarray, orientation: str) -> int:
        """Đếm số đường kẻ dài theo 1 hướng bằng morphological erode+dilate.

        Ý tưởng: 1 kernel dài và mỏng (vd 1x40 pixel) chỉ "sống sót" qua
        erode nếu ảnh gốc có 1 đoạn thẳng liên tục dài tương đương -- chữ
        viết thường (kể cả gạch chân) không đủ dài liên tục để sống sót,
        chỉ đường kẻ bảng mới đủ.
        """
        h, w = binary.shape
        if orientation == "horizontal":
            kernel_len = max(w // 30, 20)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
        else:
            kernel_len = max(h // 30, 20)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_len))

        eroded = cv2.erode(binary, kernel, iterations=1)
        lines_mask = cv2.dilate(eroded, kernel, iterations=1)

        contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return len(contours)

    def classify_pages(self, images: List[Image.Image]) -> List[bool]:
        """Trả về list bool song song với `images` -- True nếu trang đó có bảng."""
        return [self.page_has_table(img) for img in images]


if __name__ == "__main__":
    import sys
    from pdf2image import convert_from_path

    if len(sys.argv) > 1:
        images = convert_from_path(sys.argv[1], dpi=200)
        detector = PageTypeDetectorScan()
        for i, img in enumerate(images, start=1):
            has_table = detector.page_has_table(img)
            print(f"Trang {i}: {'CÓ BẢNG' if has_table else 'text thuần'}")
    else:
        print("Sử dụng: python page_type_detector_scan.py <duong_dan_file.pdf>")