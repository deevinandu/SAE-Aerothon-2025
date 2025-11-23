# SAE Aerothon 2025 - Ground Control Station

<div align="center">

**Advanced Multi-Drone Ground Control Station with AI-Powered Vision Analysis**

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [Documentation](#-documentation)

</div>

---

## Overview

SAE Aerothon 2025 GCS is a next-generation ground control station designed for autonomous multi-drone operations with real-time AI-powered disaster detection and response capabilities. Built for the SAE Aerothon competition, it provides comprehensive drone fleet management, mission planning, and intelligent video analysis.

### Key Capabilities

- **Multi-Drone Swarm Management** - Control and monitor multiple drones simultaneously
- **AI Vision Analysis** - Real-time disaster detection using Google Gemini Vision API
- **Live Video Streaming** - UDP/RTSP video with recording and AI annotation
- **Mission Planning** - KML-based autonomous mission generation
- **Real-Time Telemetry** - Live flight data visualization and monitoring
- **Data Persistence** - Comprehensive event logging and flight recording
- **Auto-Reconnection** - Resilient communication with automatic recovery

---

## Features

### Ground Control Station (GCS)

#### Backend (Python/FastAPI)
- **MAVLink Communication** - Full MAVLink protocol support for ArduPilot/PX4
- **Swarm Manager** - Multi-drone coordination and telemetry aggregation
- **Gemini Vision Integration** - AI-powered image analysis for disaster detection
- **Video Management** - Multi-source video streaming (UDP, RTSP, File, Webcam)
- **Mission Controller** - Automated mission upload and execution
- **Event Logger** - SQLite-based mission event and flight log storage
- **Video Recorder** - Frame capture with AI analysis overlay

#### Frontend (Next.js/React/TypeScript)
- **Real-Time Dashboard** - Live video feed with telemetry overlay
- **Swarm Overview** - Fleet status and drone selection interface
- **Mission Control** - KML upload and mission management
- **Telemetry Widgets** - Altitude, speed, battery, GPS visualization
- **AI Reasoning Display** - Live disaster detection results
- **Recording Controls** - Start/stop video recording with metadata
- **Connection Dialog** - Easy MAVLink configuration (UDP/TCP/Serial)

### Raspberry Pi Companion Computer

- **Camera Streaming** - H.264 encoded UDP video transmission
- **MAVLink Relay** - Bidirectional telemetry forwarding
- **System Monitoring** - Health checks and resource monitoring
- **Auto-Start Service** - Systemd integration for boot-time startup

---

## Quick Start

### Prerequisites

- **Python 3.8+** (Backend)
- **Node.js 18+** (Frontend)
- **Google Gemini API Key** ([Get one here](https://ai.google.dev/))
- **MAVLink-compatible drone** or SITL simulator

### Installation

#### 1. Clone Repository
```bash
git clone https://github.com/yourusername/SAE-Aerothon-2025.git
cd SAE-Aerothon-2025
```

#### 2. Backend Setup
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

#### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Build and start
npm run dev
```

#### 4. Start Services

**Option A: Start All (Windows)**
```bash
# From project root
start_all.bat
```

**Option B: Manual Start**
```bash
# Terminal 1: Backend
cd backend
python main.py

# Terminal 2: Frontend
cd frontend
npm run dev
```

### Access the GCS

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

---

## Configuration

### Backend (.env)

```env
# Gemini AI Configuration
GEMINI_API_KEY=your_api_key_here
ROBOTICS_MODEL=gemini-2.0-flash-exp
GEMINI_DEBUG=false

# Logging
LOG_LEVEL=INFO

# Video Source (udp, rtsp, file, webcam)
VIDEO_SOURCE=udp://0.0.0.0:5600
```

### Frontend (.env.local)

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

### RPi Companion (config.yaml)

```yaml
camera:
  resolution: [1280, 720]
  framerate: 30
  format: h264

network:
  gcs_ip: 192.168.1.100
  video_port: 5600
  mavlink_port: 14550

mavlink:
  serial_port: /dev/ttyAMA0
  baud_rate: 57600
```

---

## Usage

### Connecting to a Drone

1. **Click "MAVLink" button** in the navbar
2. **Select connection type:**
   - **UDP**: For SITL or network drones (e.g., `127.0.0.1:14550`)
   - **TCP**: For TCP connections
   - **Serial**: For direct USB connection (e.g., `COM3`, `57600` baud)
3. **Click "Connect"**

### Starting a Mission

1. **Prepare KML file** with mission waypoints
2. **Click "Mission Control"** in the dashboard
3. **Upload KML file**
4. **Set parameters:**
   - Altitude (meters)
   - Speed (m/s)
   - Auto-start option
5. **Click "Upload & Start Mission"**

### Recording Video

1. **Click the Record button** (red circle) in navbar
2. **Recording starts** with timestamp overlay
3. **AI detections** are logged in real-time
4. **Click Stop** (square) to end recording
5. **Files saved** in `backend/recordings/`

### Viewing Events

Access logged events via API:
```bash
# Get all events for a session
curl http://localhost:8000/events/{session_id}

# Export events as CSV
curl http://localhost:8000/events/export/{session_id}?format=csv

# Get event statistics
curl http://localhost:8000/events/stats/{session_id}
```

---

## Project Structure

```
SAE-Aerothon-2025/
├── backend/                    # Python FastAPI backend
│   ├── main.py                # Main application entry
│   ├── swarm_manager.py       # Multi-drone management
│   ├── gemini_vision.py       # AI vision service
│   ├── video_stream.py        # Video streaming
│   ├── video_recorder.py      # Recording with AI logs
│   ├── mission_controller.py  # Mission automation
│   ├── event_logger.py        # Event persistence
│   ├── database.py            # SQLite models
│   └── requirements.txt       # Python dependencies
│
├── frontend/                   # Next.js React frontend
│   ├── src/
│   │   ├── pages/
│   │   │   └── dashboard/     # Main dashboard
│   │   └── components/        # React components
│   │       ├── DroneSelector.tsx
│   │       ├── FleetOverview.tsx
│   │       ├── ConnectionDialog.tsx
│   │       └── TelemetryWidget.tsx
│   └── package.json
│
├── rpi_companion/             # Raspberry Pi software
│   ├── main.py               # Main orchestrator
│   ├── camera_streamer.py    # Video streaming
│   ├── mavlink_relay.py      # Telemetry relay
│   ├── system_monitor.py     # Health monitoring
│   ├── config.yaml           # Configuration
│   └── install.sh            # Setup script
│
├── recordings/                # Video recordings (auto-created)
├── gcs.db                    # SQLite database (auto-created)
└── README.md                 # This file
```

---

## 🔌 API Endpoints

### Swarm Management
- `GET /swarm/status` - Get all drone statuses
- `GET /swarm/drone/{sys_id}` - Get specific drone info
- `GET /swarm/telemetry/{sys_id}` - Get drone telemetry

### Mission Control
- `POST /mission/start` - Upload and start mission
- `POST /mission/upload` - Upload mission only
- `POST /mission/manual` - Manual mission upload

### Telemetry
- `POST /telemetry/connect` - Connect to MAVLink
- `POST /telemetry/disconnect` - Disconnect from MAVLink
- `GET /telemetry/sensors` - Get sensor data

### Video
- `GET /video/feed` - Video stream endpoint
- `POST /video/source` - Change video source
- `GET /video/sources` - List available sources

### Recording
- `POST /recording/start` - Start recording
- `POST /recording/stop` - Stop recording
- `GET /recording/status` - Get recording status
- `GET /recording/list` - List all recordings

### Events
- `GET /events/{session_id}` - Get session events
- `GET /events/export/{session_id}` - Export events
- `GET /events/stats/{session_id}` - Event statistics

---

## AI Features

### Disaster Detection

The system uses Google Gemini Vision API to analyze video frames in real-time:

- **Fire Detection** - Identifies flames and smoke
- **Flood Detection** - Detects water accumulation
- **Structural Damage** - Identifies collapsed buildings
- **Safe Landing Spots** - Suggests safe areas for emergency landing

### Event Logging

All AI detections are automatically logged with:
- Timestamp
- Disaster type
- Confidence score
- GPS coordinates
- Safe landing spot recommendations

---

## Development

### Running Tests
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

### Building for Production

**Backend:**
```bash
cd backend
# Use gunicorn or uvicorn for production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Frontend:**
```bash
cd frontend
npm run build
npm start
```

---

## Database Schema

### Tables

- **`mission_events`** - Disaster detections and mission events
- **`flight_logs`** - Flight session metadata and statistics
- **`recording_metadata`** - Video recording information

---

## Troubleshooting

### Video Stream Issues
- Ensure correct `VIDEO_SOURCE` in `.env`
- Check firewall allows UDP port 5600
- Verify RPi companion is streaming

### MAVLink Connection Failed
- Confirm correct port and baud rate
- Check drone/SITL is running
- Verify no other GCS is connected

### AI Analysis Not Working
- Verify `GEMINI_API_KEY` is set correctly
- Check API quota limits
- Review backend logs for errors

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Ground Control Station                    │
├──────────────────────┬──────────────────────────────────────┤
│   Frontend (Next.js) │      Backend (FastAPI)               │
│                      │                                       │
│  • Dashboard UI      │  • SwarmManager (Multi-drone)        │
│  • Video Display     │  • Gemini Vision Service             │
│  • Telemetry Widgets │  • VideoManager (Multi-source)       │
│  • Mission Control   │  • MissionController                 │
│  • Fleet Overview    │  • EventLogger                       │
│                      │  • VideoRecorder                     │
└──────────────────────┴──────────────────────────────────────┘
                              ▲
                              │ MAVLink (UDP/TCP/Serial)
                              │ Video Stream (UDP/RTSP)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Raspberry Pi Companion Computer                 │
├─────────────────────────────────────────────────────────────┤
│  • Camera Streamer (H.264/UDP)                              │
│  • MAVLink Relay (Bidirectional)                            │
│  • System Monitor                                           │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ MAVLink (Serial/UART)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Flight Controller                         │
│                  (ArduPilot/PX4)                            │
└─────────────────────────────────────────────────────────────┘
```
---

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

</div>
