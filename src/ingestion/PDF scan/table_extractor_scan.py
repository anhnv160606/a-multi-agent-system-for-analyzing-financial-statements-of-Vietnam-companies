"""Trích BẢNG (và text đi kèm) từ trang PDF scan CÓ chứa bảng.
"""

import io
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from pdf2image import convert_from_path

from src.ingestion.models import ExtractedTable, PageContent
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.scan.table_extractor_scan")


class TableExtractorScan:
    def __init__(self, lang: str = "vi"):
        self.lang = lang
        self._table_engine = None

    def _init_table_engine(self):
        """Lazy-load PPStructure ĐẦY ĐỦ (khác engine layout-only của
        page_type_detector_scan.py -- engine đó không trả nội dung bảng)."""
        if self._table_engine is None:
            try:
                from paddleocr import PPStructure
                self._table_engine = PPStructure(show_log=False, lang=self.lang)
            except ImportError as e:
                raise ImportError(
                    "Cần cài đặt paddleocr: "
                    "pip install paddleocr paddlepaddle --break-system-packages"
                ) from e
        return self._table_engine

    def extract_page(
        self, image: Image.Image, page_num: int, pdf_path: str = ""
    ) -> Tuple[List[ExtractedTable], PageContent]:
        """Trả về (danh sách bảng, text còn lại của trang) cho MỘT trang.

        Text trả về ở đây LÀ text hợp lệ của trang (title, đoạn văn ngắn đi
        kèm bảng...) -- không phải nội dung bảng bị đọc nhầm. Nên đưa thẳng
        page_content này vào SplitDocument.texts, không cần chạy lại
        text_extractor_scan.py cho trang này.
        """
        engine = self._init_table_engine()
        img_np = np.array(image.convert("RGB"))
        result = engine(img_np)

        tables: List[ExtractedTable] = []
        text_regions: List[Tuple[float, str]] = []
        table_idx = 0

        for region in result:
            rtype = region.get("type")
            bbox = region.get("bbox") or [0, 0, 0, 0]

            if rtype == "table":
                html = region.get("res", {}).get("html")
                if not html:
                    continue
                rows = self._html_table_to_rows(html)
                if not rows:
                    continue

                table_idx += 1
                headers, data_rows = rows[0], rows[1:]
                tables.append(
                    ExtractedTable(
                        page_num=page_num,
                        table_index=table_idx,
                        headers=headers,
                        rows=data_rows,
                        markdown=self._to_markdown(headers, data_rows),
                        csv=self._to_csv(headers, data_rows),
                        bbox=tuple(bbox),
                        title=None,
                        extraction_engine="ppstructure",
                        metadata={"num_rows": len(data_rows), "num_cols": len(headers)},
                    )
                )
                continue

            # Vùng không phải bảng: PPStructure đã tự OCR sẵn trong "res"
            res = region.get("res")
            if isinstance(res, list):
                lines = [
                    item["text"] for item in res
                    if isinstance(item, dict) and "text" in item
                ]
                if lines:
                    text_regions.append((bbox[1], "\n".join(lines)))

        # Ráp text theo đúng thứ tự từ trên xuống
        text_regions.sort(key=lambda r: r[0])
        full_text = "\n".join(t[1] for t in text_regions)

        page_content = PageContent(
            page_num=page_num,
            text=full_text,
            extraction_engine="ppstructure",
            layout_info={"source": pdf_path, "num_tables": len(tables)},
        )

        return tables, page_content

    def _html_table_to_rows(self, html: str) -> List[List[str]]:
        try:
            dfs = pd.read_html(html)
            if not dfs:
                return []
            df = dfs[0]
            header_row = [str(c) for c in df.columns.tolist()]
            data_rows = df.astype(str).values.tolist()
            return [header_row] + data_rows
        except Exception as e:
            logger.warning(f"Lỗi parse HTML bảng từ PPStructure: {e}")
            return []

    def _to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def _to_csv(self, headers: List[str], rows: List[List[str]]) -> str:
        df = pd.DataFrame(rows, columns=headers)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue()

    def extract_from_pages(
        self, pdf_path: str, page_numbers: List[int], dpi: int = 300
    ) -> Dict[int, Tuple[List[ExtractedTable], PageContent]]:
        """Trích bảng+text cho các trang chỉ định (đã xác nhận có bảng).

        Dùng khi gọi độc lập/test. Trong pipeline_scan.py thực tế, nên gọi
        extract_page() trực tiếp trên ảnh đã convert sẵn để tránh
        convert_from_path() 2 lần cho cùng 1 file.
        """
        images = convert_from_path(pdf_path, dpi=dpi)
        results: Dict[int, Tuple[List[ExtractedTable], PageContent]] = {}
        for page_num in page_numbers:
            idx = page_num - 1
            if idx < 0 or idx >= len(images):
                logger.warning(f"Trang {page_num} vượt phạm vi file.")
                continue
            results[page_num] = self.extract_page(images[idx], page_num, pdf_path=pdf_path)
        return results