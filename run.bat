@echo off
title EPMNote

cd /d C:\10_dev\EPMNote
set PYTHONPATH=C:\10_dev\EPMNote

echo.
echo ========================================
echo   EPMNote - Starting...
echo ========================================
echo.
echo Browser will open automatically.
echo Press Ctrl+C to stop.
echo.

start http://localhost:8501

python -m streamlit run src/app.py --server.port 8501 --server.headless true

pause
