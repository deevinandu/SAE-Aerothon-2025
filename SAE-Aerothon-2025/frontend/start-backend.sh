#!/bin/bash
echo "Starting SAE Aerothon GCS Backend..."
echo

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r backend/requirements.txt

# Check for .env file
if [ ! -f "backend/.env" ]; then
    echo
    echo "WARNING: backend/.env file not found!"
    echo "Please copy backend/.env.example to backend/.env and configure your GEMINI_API_KEY"
    echo
    exit 1
fi

# Start the backend server
echo
echo "Starting backend server on http://localhost:8000"
echo "Press Ctrl+C to stop the server"
echo
cd backend
python main.py