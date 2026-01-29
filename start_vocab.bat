@echo off
echo ====================================
echo Vocabulary App Launcher
echo ====================================
echo.

REM Change to your app folder
cd /d "D:\vocabulary-app"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Install Python from python.org
    pause
    exit
)

REM Install required packages
echo Installing/updating packages...
pip install flask flask-cors pandas openpyxl --quiet

REM Start the server
echo.
echo Starting Vocabulary App...
echo.
echo ACCESS FROM:
echo • This PC:   http://localhost:8000
echo • Phone:     http://192.168.0.104:8000
echo.
echo ====================================
python server.py

pause