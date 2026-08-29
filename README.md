# 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy Hệ Thống

---

## 🔑 1. Cấu Hình Biến Môi Trường (`.env`)

Tạo file **`.env`** tại thư mục gốc của dự án và điền các API Key:

```env
# API Key của Groq (bắt buộc)
GROQ_API_KEY="gsk_..."

# API Key của Google Gemini (tuỳ chọn)
GOOGLE_API_KEY="AIza..."

# Token nhúng Vector của Jina AI (bắt buộc)
JINA_TOKEN="jina_..."

# Cấu hình Web
PORT=3000
STREAM_REPORT_TOKENS=1
PYTHONIOENCODING=utf-8
```

---

## 🐳 2. Cách 1: Chạy Bằng Docker (Khuyên Dùng — 1 Thao Tác)

### Bước 1: Mở phần mềm Docker Desktop
* Bật ứng dụng **Docker Desktop** trên máy tính của bạn và chờ Docker khởi động xong *(hiển thị trạng thái màu xanh: Engine running)*.

### Bước 2: Khởi động hệ thống
* **Trên Windows:** Click đúp chuột vào file [`start_docker.bat`](start_docker.bat).
* **Hoặc dùng lệnh Terminal:**
  ```bash
  docker compose up -d --build
  ```

### Bước 3: Truy cập Web để sử dụng
* Mở trình duyệt và truy cập: 👉 **`http://localhost:3000`**

### 🛑 Tắt hệ thống Docker:
* Click đúp chuột vào file [`stop_docker.bat`](stop_docker.bat) hoặc chạy lệnh:
  ```bash
  docker compose down
  ```

### 📋 Xem Logs hoạt động:
* Chạy lệnh:
  ```bash
  docker compose logs -f
  ```
  *(Hoặc xem trực tiếp trong tab Logs của container `finagent_system` trên Docker Desktop).*

---

## 💻 3. Cách 2: Chạy Trực Tiếp Trên Máy (Local Development)

### Bước 1: Tạo và kích hoạt môi trường ảo Python
```bash
python -m venv .venv

# Kích hoạt trên Windows:
.\.venv\Scripts\Activate.ps1

# Kích hoạt trên Linux/macOS:
source .venv/bin/activate
```

### Bước 2: Cài đặt các thư viện cần thiết
```bash
python -m pip install -U pip
pip install -r requirements-docker.txt
pip install langchain-text-splitters markdown2
```

### Bước 3: Nạp và xử lý toàn bộ dữ liệu tài chính (CSV + PDF)
```bash
python scripts/ingest_all_data.py
```

### Bước 4: Chạy script kiểm thử tự động (End-to-End Pipeline)
```bash
python test_full_pipeline.py
```
*Báo cáo kết quả sẽ được tạo tại thư mục `reports/`.*

### Bước 5: Khởi chạy Giao diện Web trên Local
```bash
# 1. Cài đặt và build giao diện Frontend
cd frontend
npm install
npm run build
cd ..

# 2. Cài đặt và khởi chạy Backend Server
cd backend
npm install
npm start
```
* Mở trình duyệt tại: 👉 **`http://localhost:3000`**