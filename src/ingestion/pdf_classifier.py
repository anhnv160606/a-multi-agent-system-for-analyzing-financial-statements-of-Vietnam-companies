"""Module phân loại định dạng PDF (Scanned Image vs Native Digital PDF)."""
from pathlib import Path
from typing import Any, Dict, Literal
import pdfplumber

# Các phần mềm scanner/máy in/OCR thường xuất hiện trong metadata của file scan
SCANNER_METADATA_KEYWORDS = [
    "scan",
    "scanner",
    "camscanner",
    "xerox",
    "canon",
    "epson",
    "ricoh",
    "fujitsu",
    "brother",
    "hp scan",
    "image",
    "paperless",
]


def _check_metadata_heuristic(metadata: Dict[str, Any]) -> bool:
  """Kiểm tra xem metadata có chứa từ khóa của các công cụ scan hay không.

  Returns True nếu có dấu hiệu máy scan.
  """
  if not metadata:
    return False

  fields_to_check = [
      str(metadata.get("Producer", "")).lower(),
      str(metadata.get("Creator", "")).lower(),
      str(metadata.get("Author", "")).lower(),
  ]

  for field in fields_to_check:
    for keyword in SCANNER_METADATA_KEYWORDS:
      if keyword in field:
        return True
  return False


def classify_pdf(
    pdf_path: str,
    min_chars_per_page: int = 50,
    max_pages_to_check: int = 5,
    min_valid_page_ratio: float = 0.5,
) -> Literal["scan", "native"]:
  """Tự động phân loại tài liệu PDF thành dạng 'scan' hoặc 'native'.

  Args:
      pdf_path: Đường dẫn tới file PDF cần kiểm tra.
      min_chars_per_page: Số lượng ký tự text tối thiểu trên một trang để coi
        trang đó có text layer hợp lệ.
      max_pages_to_check: Số trang đầu tiên cần duyệt (để tối ưu tốc độ đọc file
        lớn).
      min_valid_page_ratio: Tỷ lệ các trang hợp lệ tối thiểu trên tổng số trang
        được kiểm tra.

  Returns:
      "native": File PDF kỹ thuật số có sẵn text layer (có thể trích xuất văn
      bản trực tiếp).
      "scan": File PDF dạng quét từ ảnh, cần qua pipeline OCR (Docling /
      Tesseract).
  """
  path = Path(pdf_path)
  if not path.is_file():
    raise FileNotFoundError(f"Không tìm thấy file PDF tại: {pdf_path}")

  try:
    with pdfplumber.open(path) as pdf:
      total_pages = len(pdf.pages)
      if total_pages == 0:
        return "scan"

      # Giới hạn số trang cần quét để kiểm tra
      pages_to_scan = min(total_pages, max_pages_to_check)
      valid_text_pages = 0

      for i in range(pages_to_scan):
        page = pdf.pages[i]
        # Trích xuất text từ trang
        text = page.extract_text() or ""
        # Loại bỏ khoảng trắng thừa để đếm ký tự thực tế
        cleaned_text = "".join(text.split())

        if len(cleaned_text) >= min_chars_per_page:
          valid_text_pages += 1

      valid_ratio = valid_text_pages / pages_to_scan

      # Heuristic 1: Dựa trên mật độ text extract được
      if valid_ratio >= min_valid_page_ratio:
        return "native"

      # Heuristic 2: Phụ trợ kiểm tra metadata nếu text ở ngưỡng ranh giới
      # Nếu text quá ít nhưng metadata chỉ rõ từ máy scan -> chắc chắn là scan
      pdf_metadata = pdf.metadata or {}
      if _check_metadata_heuristic(pdf_metadata):
        return "scan"

      return "scan"

  except Exception as e:
    # Nếu file lỗi format hoặc bị mã hóa không mở được bằng pdfplumber
    # Mặc định trả về 'scan' để đẩy sang engine OCR xử lý fallback
    print(f"Lỗi khi đọc file PDF {pdf_path}: {e}")
    return "scan"


if __name__ == "__main__":
  # Block test nhanh module
  import sys

  if len(sys.argv) > 1:
    target_file = sys.argv[1]
    result = classify_pdf(target_file)
    print(f"File: {target_file} -> Phân loại: {result.upper()}")
  else:
    print("Sử dụng: python src/ingestion/pdf_classifier.py <duong_dan_file_pdf>")