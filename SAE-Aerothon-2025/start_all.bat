@echo off
echo Starting GCS System...

:: Start Backend
start "GCS Backend" cmd /k "cd backend && python main.py"

:: Start Frontend
start "GCS Frontend" cmd /k "cd frontend && npm run dev"

echo System started!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
