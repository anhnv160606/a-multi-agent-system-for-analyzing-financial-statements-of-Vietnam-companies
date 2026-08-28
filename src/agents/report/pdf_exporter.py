"""PDF Exporter — Chuyển Markdown báo cáo → PDF hoặc HTML (fallback).

Chiến lược:
    Markdown → HTML (dùng markdown2) → PDF (dùng weasyprint nếu available).
    Fallback: nếu weasyprint không install được → lưu file .html thay thế.

Task: 4.11 (feature_list.md)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("src.agents.report.pdf_exporter")

# CSS cơ bản cho báo cáo
_REPORT_CSS = """
body {
    font-family: 'Times New Roman', Times, serif;
    font-size: 12pt;
    line-height: 1.6;
    max-width: 800px;
    margin: 40px auto;
    padding: 20px;
    color: #222;
}
h1 { font-size: 20pt; color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; }
h2 { font-size: 15pt; color: #16213e; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 24px; }
h3 { font-size: 13pt; color: #0f3460; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 10pt; }
th { background-color: #1a1a2e; color: white; padding: 8px 10px; text-align: left; }
td { border: 1px solid #ddd; padding: 6px 10px; }
tr:nth-child(even) { background-color: #f5f5f5; }
ul, ol { margin: 8px 0; padding-left: 24px; }
li { margin: 4px 0; }
em { color: #555; font-size: 10pt; }
strong { color: #1a1a2e; }
blockquote { border-left: 4px solid #1a1a2e; margin: 0; padding-left: 16px; color: #555; }
hr { border: none; border-top: 1px solid #ccc; margin: 20px 0; }
@media print {
    body { margin: 20px; }
    h1, h2 { page-break-after: avoid; }
    table { page-break-inside: avoid; }
}
"""


class PDFExporter:
    """Chuyển Markdown báo cáo thành PDF (hoặc HTML nếu weasyprint không có).

    Usage:
        exporter = PDFExporter()
        output_path = exporter.export(markdown_text, "output/report.pdf")
        print(f"Saved to: {output_path}")
    """

    def __init__(self, css: str | None = None) -> None:
        """
        Args:
            css: CSS tùy chỉnh. Nếu None → dùng _REPORT_CSS mặc định.
        """
        self.css = css or _REPORT_CSS
        self._weasyprint_available = self._check_weasyprint()
        self._markdown2_available = self._check_markdown2()

    # =========================================================================
    # Public API
    # =========================================================================

    def export(self, markdown_text: str, output_path: str) -> str:
        """Chuyển Markdown → PDF (hoặc HTML fallback) và lưu file.

        Args:
            markdown_text: Nội dung Markdown báo cáo.
            output_path:   Đường dẫn file đích (ví dụ: "reports/VNM_2023.pdf").
                           Nếu weasyprint không có, extension tự đổi thành .html.

        Returns:
            Đường dẫn file thực tế đã lưu.
        """
        html_content = self._md_to_html(markdown_text)

        # Tạo thư mục nếu chưa có
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if self._weasyprint_available:
            actual_path = self._html_to_pdf(html_content, str(output_file))
        else:
            # Fallback: lưu HTML
            html_path = output_file.with_suffix(".html")
            actual_path = self._save_html(html_content, str(html_path))
            logger.info(
                "pdf_exporter: weasyprint not available — saved as HTML fallback",
                extra={"event": "pdf_fallback", "path": actual_path},
            )

        logger.info(
            "pdf_exporter: export complete",
            extra={"event": "export_done", "path": actual_path, "size_bytes": os.path.getsize(actual_path)},
        )
        return actual_path

    def export_html(self, markdown_text: str, output_path: str) -> str:
        """Luôn xuất HTML (không phụ thuộc weasyprint).

        Args:
            markdown_text: Nội dung Markdown.
            output_path:   Đường dẫn .html.

        Returns:
            Đường dẫn file HTML đã lưu.
        """
        html_content = self._md_to_html(markdown_text)
        html_path = Path(output_path).with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        return self._save_html(html_content, str(html_path))

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _md_to_html(self, markdown_text: str) -> str:
        """Chuyển Markdown → HTML đầy đủ với CSS styling.

        Dùng markdown2 nếu có, fallback về xử lý cơ bản nếu không có.
        """
        if self._markdown2_available:
            import markdown2  # type: ignore
            body_html = markdown2.markdown(
                markdown_text,
                extras=["tables", "fenced-code-blocks", "strike", "header-ids"],
            )
        else:
            # Minimal fallback: chỉ convert line breaks và wrap trong <pre>
            logger.warning(
                "pdf_exporter: markdown2 not installed — using minimal HTML conversion",
                extra={"event": "markdown2_missing"},
            )
            escaped = markdown_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            body_html = f"<pre style='white-space:pre-wrap;font-family:serif'>{escaped}</pre>"

        full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bao cao Phan tich Tai chinh</title>
    <style>
{self.css}
    </style>
</head>
<body>
{body_html}
</body>
</html>"""
        return full_html

    def _html_to_pdf(self, html_content: str, output_path: str) -> str:
        """Chuyển HTML → PDF dùng weasyprint.

        Args:
            html_content: Chuỗi HTML đầy đủ.
            output_path:  Đường dẫn file .pdf.

        Returns:
            Đường dẫn file PDF đã lưu.
        """
        try:
            import weasyprint  # type: ignore
            pdf_path = Path(output_path).with_suffix(".pdf")
            weasyprint.HTML(string=html_content).write_pdf(str(pdf_path))
            return str(pdf_path)
        except Exception as exc:
            logger.warning(
                f"pdf_exporter: weasyprint PDF generation failed: {exc} — falling back to HTML",
                extra={"event": "weasyprint_error"},
            )
            html_path = Path(output_path).with_suffix(".html")
            return self._save_html(html_content, str(html_path))

    def _save_html(self, html_content: str, output_path: str) -> str:
        """Lưu HTML ra file.

        Returns:
            Đường dẫn file đã lưu (string).
        """
        html_file = Path(output_path)
        html_file.write_text(html_content, encoding="utf-8")
        return str(html_file)

    # =========================================================================
    # Availability checks
    # =========================================================================

    @staticmethod
    def _check_weasyprint() -> bool:
        """Kiểm tra weasyprint đã install chưa."""
        try:
            import weasyprint  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_markdown2() -> bool:
        """Kiểm tra markdown2 đã install chưa."""
        try:
            import markdown2  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False
