@echo off
echo Starting SAE Aerothon GCS Backend...
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo Installing requirements...
pip install -r backend\requirements.txt

REM Check for .env file
if not exist "backend\.env" (
    echo.
    echo WARNING: backend\.env file not found!
    echo Please copy backend\.env.example to backend\.env and configure your GEMINI_API_KEY
    echo.
    pause
    exit /b 1
)

REM Start the backend server
echo.
echo Starting backend server on http://localhost:8000
echo Press Ctrl+C to stop the server
echo.
cd backend
python main.py