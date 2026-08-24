import pandas as pd
from src.ingestion.models import ExtractedTable
from typing import List
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.CSV.csv_loader")

class CSVFinancialLoader:
    @staticmethod
    def _read_csv_file(file_path: str, table_index: int, title: str) -> ExtractedTable:
        if not Path(file_path).exists():
            logger.error(f"File {file_path} does not exist.")
            raise FileNotFoundError(f"File {file_path} does not exist.")

        df = pd.read_csv(file_path, dtype=str, skiprows=7, keep_default_na=False)  # Skip first 3 rows, treat all as strings
        headers = df.columns.tolist()
        rows = df.values.tolist()
        try:
            markdown_str = df.to_markdown(index=False)
        except ImportError:
            logger.warning("Tabulate package not installed yet. Markdown representation will be empty.")
            markdown_str = df.to_csv(index=False, sep='|')
        csv_str = df.to_csv(index=False)
        return ExtractedTable(
            page_num=1,
            table_index=table_index,
            headers=headers,
            rows=rows,
            markdown=markdown_str,
            csv=csv_str,
            bbox=None,
            title=title,
            extraction_engine="csv",
            metadata={ "source_file": str(file_path), "report_type": title}
        )

    def load_company_financials(self, bs_path: str, is_path: str, cf_path: str) -> List[ExtractedTable]:
        tables: List[ExtractedTable] = []
        if bs_path:
            bs_table = self._read_csv_file(bs_path, table_index=1, title="Balance Sheet")
            tables.append(bs_table)
        if is_path:
            is_table = self._read_csv_file(is_path, table_index=2, title="Income Statement")
            tables.append(is_table)
        if cf_path:
            cf_table = self._read_csv_file(cf_path, table_index=3, title="Cash Flow Statement")
            tables.append(cf_table)

        return tables

if __name__ == "__main__":
    import os

    # 1. Khai báo đường dẫn tới các file dữ liệu thật
    # (Đảm bảo 3 file này đang nằm cùng thư mục với file script, 
    # hoặc bạn cần sửa lại đường dẫn tuyệt đối/tương đối cho đúng)
    fpt_bs = "data/FPT_BS.csv"
    fpt_is = "data/FPT_IS.csv"
    fpt_cf = "data/FPT_CF.csv"

    # Kiểm tra nhanh xem file có tồn tại không trước khi chạy
    missing_files = [f for f in [fpt_bs, fpt_is, fpt_cf] if not os.path.exists(f)]
    if missing_files:
        print(f"Cảnh báo: Không tìm thấy các file sau: {', '.join(missing_files)}")
        print("Vui lòng đảm bảo các file này đã được đặt đúng thư mục.")
    else:
        print("Đã tìm thấy đủ 3 file. Bắt đầu load dữ liệu...\n")

        # 2. Khởi tạo Loader và load dữ liệu
        try:
            loader = CSVFinancialLoader()
            extracted_tables = loader.load_company_financials(
                bs_path=fpt_bs, 
                is_path=fpt_is, 
                cf_path=fpt_cf
            )

            # 3. Kiểm tra kết quả (Verify)
            print(f"Tổng số bảng đã load thành công: {len(extracted_tables)}")
            
            for t in extracted_tables:
                print(f"\n{'='*60}")
                print(f"--- {t.title} (Page: {t.page_num}, Index: {t.table_index}) ---")
                print(f"Engine: {t.extraction_engine}")
                print(f"File nguồn: {t.metadata.get('source_file')}")
                print(f"Số lượng cột: {len(t.headers)} | Headers: {t.headers}")
                print(f"Tổng số dòng dữ liệu: {len(t.rows)}")
                
                if t.rows:
                    print(f"\nRow đầu tiên (raw string):")
                    print(t.rows[0])
                
                # Chuyển thành dict và chỉ in 2 dòng đầu tiên để không bị loạn console
                records = t.to_dict_records()
                print(f"\nHiển thị 2 bản ghi đầu tiên (trên tổng số {len(records)}):")
                for rec in records[:2]:
                    print("  ", rec)

        except Exception as e:
            print(f"Đã xảy ra lỗi trong quá trình đọc file: {e}")

    


        

