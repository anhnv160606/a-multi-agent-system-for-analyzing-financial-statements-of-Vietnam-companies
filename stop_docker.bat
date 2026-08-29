@echo off
chcp 65001 > nul
echo ======================================================================
echo  🛑 Đang dừng hệ thống FinAgent AI...
echo ======================================================================
docker compose down
echo.
echo  ✅ Đã dừng container an toàn!
pause
