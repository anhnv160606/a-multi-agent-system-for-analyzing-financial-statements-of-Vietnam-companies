@echo off
chcp 65001 > nul
echo ======================================================================
echo  🚀 Đang khởi chạy hệ thống FinAgent AI với Docker Compose...
echo ======================================================================
docker compose up -d --build
echo.
echo ======================================================================
echo  ✅ FinAgent đã khởi chạy thành công!
echo  👉 Mở trình duyệt tại: http://localhost:3000
echo ======================================================================
pause
