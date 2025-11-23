import base64
import io
import json
import os
import time
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio

# Import Video and AI services
from video_stream import VideoManager
from gemini_vision import GeminiVisionService
from mission_controller import MissionController
from video_recorder import VideoRecorder
import requests
import random
import math
from datetime import datetime
import threading

# Import telemetry fetchers
from telemetry_fetchers import get_telemetry_manager, shutdown_telemetry_manager, get_global_mavlink_master
from telemetry_config import telemetry_connection_settings

# Import database module
import database
from sqlalchemy.orm import Session
from fastapi import Depends

# Import path creation module
from path_planner import load_kml_boundary, Polygon, Point, generate_surveillance_path
import waypoint_mission as waypoint_mission
from mavproxy_router import start_mavproxy, stop_mavproxy
from event_logger import event_logger

# Import fleet manager
from swarm_manager import SwarmManager, parse_kml_coordinates, MissionItem


load_dotenv()

app = FastAPI(title="SAE Aerothon GCS Backend", version="1.0.0")

# Allow local development origins by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ROBOTICS_MODEL = os.getenv("ROBOTICS_MODEL", "models/gemini-robotics-er-1.5-preview")
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "").lower() in {"1", "true", "yes"}

# Logging configuration
log_level_name = os.getenv("LOG_LEVEL", "DEBUG" if GEMINI_DEBUG else "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("main")
logger.info("Gemini AI configured with model: %s", ROBOTICS_MODEL)


# Session storage is now handled by database.py
# Global cache for active session objects (optional, for performance)
# recording_sessions: Dict[str, Dict[str, Any]] = {} 
SESSION_TIMEOUT = timedelta(hours=1)  # Auto-cleanup after 1 hour

# Global state for MAVProxy router
MAVPROXY_ROUTER_ACTIVE = False
MAVPROXY_PORTS: Dict[str, str] = {}

# Global SwarmManager instance for multi-drone support
# Global SwarmManager instance for multi-drone support
_global_swarm_manager: Optional[SwarmManager] = None

# Global Video and AI Services
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "0")  # Default to webcam 0, can be "udp://0.0.0.0:5600"
video_manager = VideoManager(source=VIDEO_SOURCE if VIDEO_SOURCE.isdigit() else VIDEO_SOURCE if not VIDEO_SOURCE.isdigit() else int(VIDEO_SOURCE))
gemini_service = GeminiVisionService(api_key=GEMINI_API_KEY, model_name=ROBOTICS_MODEL)
video_recorder = VideoRecorder(recordings_dir="recordings")  # Initialize video recorder
mission_controller: Optional[MissionController] = None
ai_analysis_active = False

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

def ai_analysis_loop():
    """Background thread for AI analysis"""
    global ai_analysis_active
    logger.info("AI Analysis loop started")
    while True:
        if not ai_analysis_active:
            time.sleep(1)
            continue
            
        try:
            # Sample frame
            frame = video_manager.get_latest_frame_cv2()
            if frame is not None:
                # Add frame to recording if active
                video_recorder.add_frame(frame)
                
                # Analyze with Gemini
                result = gemini_service.analyze_frame(frame)
                if result:
                    # Add AI analysis to recording log
                    video_recorder.add_ai_analysis(result)
                    
                    # Broadcast result via WebSocket
                    asyncio.run(manager.broadcast(json.dumps(result)))
                    logger.debug(f"AI Analysis: {result}")
                    
                    # Check for disaster and safe landing spot
                    if result.get("disaster_detected") and result.get("safe_landing_spots"):
                        # Log disaster detection event
                        event_logger.log_disaster_detection(
                            drone_id=1,
                            disaster_type=result.get("disaster_type", "unknown"),
                            confidence=result.get("confidence", 0.0),
                            safe_spots=result.get("safe_landing_spots", [])
                        )
                        
                        if mission_controller:
                            logger.warning("🚨 DISASTER & SAFE SPOT DETECTED! TRIGGERING RESPONSE 🚨")
                            mission_controller.trigger_disaster_response(sys_id=1)
            
            # Rate limit (e.g., every 1 second)
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error in AI loop: {e}")
            time.sleep(1)


def get_swarm_manager() -> Optional[SwarmManager]:
    """Get the global SwarmManager instance."""
    return _global_swarm_manager


def init_swarm_manager(connection_strings: List[str]) -> SwarmManager:
    """Initialize or update the global SwarmManager with multiple connections."""
    global _global_swarm_manager, mission_controller
    
    # Stop existing fleet manager if it exists
    if _global_swarm_manager is not None:
        _global_swarm_manager.stop()
    
    # Create new fleet manager with multiple connections
    _global_swarm_manager = SwarmManager(connection_strings)
    _global_swarm_manager.start()
    
    # Initialize MissionController (will be set after SwarmManager is ready)
    
    logger.info(f"SwarmManager initialized with {len(connection_strings)} connection(s): {connection_strings}")
    return _global_swarm_manager

def init_mission_controller():
    global mission_controller
    fleet = get_swarm_manager()
    if fleet and not mission_controller:
        mission_controller = MissionController(fleet, connection_manager=manager)
        logger.info("MissionController initialized with ConnectionManager")


def shutdown_swarm_manager():
    """Shutdown the global SwarmManager."""
    global _global_swarm_manager
    if _global_swarm_manager is not None:
        _global_swarm_manager.stop()
        _global_swarm_manager = None
        logger.info("SwarmManager shut down")


class SessionData(BaseModel):
    """Model for session-based requests"""
    session_id: Optional[str] = None
    frame_number: int = 0
    is_first_frame: bool = False


# Telemetry Data Models - Based on actual MAVLink messages
class GPSData(BaseModel):
    """GPS_RAW_INT message data"""
    latitude: float  # degrees (lat / 1e7)
    longitude: float  # degrees (lon / 1e7)
    altitude: float  # meters (alt / 1000)
    speed: float  # m/s (vel / 100)
    heading: float  # degrees (cog / 100)
    fix_type: int  # GPS fix type (0-6)
    satellites: int  # number of satellites
    timestamp: datetime


class AttitudeData(BaseModel):
    """ATTITUDE message data"""
    roll: float  # radians
    pitch: float  # radians
    yaw: float  # radians
    rollspeed: float  # rad/s
    pitchspeed: float  # rad/s
    yawspeed: float  # rad/s
    timestamp: datetime


class VFRHUDData(BaseModel):
    """VFR_HUD message data"""
    airspeed: float  # m/s
    groundspeed: float  # m/s
    heading: float  # degrees
    throttle: float  # %
    alt: float  # meters
    climb: float  # m/s
    timestamp: datetime


class BatteryData(BaseModel):
    """BATTERY_STATUS message data"""
    voltage: float  # V (voltages[0] / 1000)
    current: float  # A (current_battery / 100)
    remaining: float  # % (battery_remaining)
    timestamp: datetime


class SystemStatus(BaseModel):
    """SYS_STATUS message data"""
    onboard_control_sensors_present: int  # bitmask
    onboard_control_sensors_enabled: int  # bitmask
    onboard_control_sensors_health: int  # bitmask
    load: float  # % (load / 10)
    voltage_battery: float  # V (voltage_battery / 1000)
    current_battery: float  # A (current_battery / 100)
    battery_remaining: int  # %
    timestamp: datetime


class TelemetryData(BaseModel):
    """Complete telemetry data package from MAVLink messages"""
    gps: GPSData
    attitude: AttitudeData
    vfr_hud: VFRHUDData
    battery: BatteryData
    system: SystemStatus
    session_id: Optional[str] = None
    timestamp: datetime
class ManualWaypoint(BaseModel):
    longitude: float
    latitude: float
    altitude: float
    mode: str

class ManualMissionRequest(BaseModel):
    waypoints: List[ManualWaypoint]
    speed: float | None = None
    end_action: str | None = None  # RTL | LAND | NONE
    auto_start: bool | None = None  # None/True -> auto start after upload
    sys_id: int | None = None  # Target specific drone in multi-drone setup
    # Optional payload drop configuration for manual missions
    drop_channel: int | None = None
    drop_pwm: int | None = None
    drop_duration_s: float | None = None



# Utility functions
def _encode_jpeg(image_bytes: bytes) -> bytes:
    """Encode image bytes as JPEG"""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    _, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return bytes(encoded)


def _extract_labels_from_text(text: str) -> List[str]:
    """Extract object labels from unstructured text using heuristics"""
    labels = []
    text_lower = text.lower()
    
    # Common object keywords
    object_keywords = [
        "person", "people", "human", "man", "woman", "child", "baby",
        "car", "truck", "bus", "vehicle", "motorcycle", "bike", "bicycle",
        "dog", "cat", "animal", "pet", "bird", "horse", "cow",
        "tree", "building", "house", "door", "window", "wall",
        "chair", "table", "desk", "bed", "sofa", "couch",
        "cup", "bottle", "glass", "plate", "bowl", "food",
        "book", "phone", "computer", "laptop", "tv", "screen",
        "bag", "backpack", "purse", "wallet", "keys",
        "ball", "toy", "game", "sport", "equipment"
    ]
    
    for keyword in object_keywords:
        if keyword in text_lower:
            labels.append(keyword)
    
    return labels[:10]

def cleanup_old_sessions():
    """Remove sessions older than SESSION_TIMEOUT"""
    # For database, we might not want to delete, just mark as inactive?
    # For now, let's just pass as we are persisting data.
    pass


def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        # Remove first fence line
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        # Remove last fence line
        if s.endswith("```"):
            s = s[: s.rfind("\n")]
    return s.strip()


def _convert_mission_items_for_fleet(raw_items: List[tuple]) -> List[MissionItem]:
    """Convert PathToMavlink mission tuples to SwarmManager MissionItem dataclasses."""
    fleet_items: List[MissionItem] = []
    for item in raw_items:
        if len(item) < 13:
            continue
        def _safe_float(val: Any, default: float = 0.0) -> float:
            try:
                return float(val)
            except (TypeError, ValueError):
                return default
        def _safe_int(val: Any, default: int = 0) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        (
            seq,
            frame,
            cmd,
            current,
            auto,
            p1,
            p2,
            p3,
            p4,
            lat,
            lon,
            alt,
            mission_type,
        ) = item[:13]
        lat = _safe_float(lat, 0.0)
        lon = _safe_float(lon, 0.0)
        alt = _safe_float(alt, 0.0)
        fleet_items.append(
            MissionItem(
                seq=_safe_int(seq),
                frame=_safe_int(frame),
                command=_safe_int(cmd),
                current=_safe_int(current),
                autocontinue=_safe_int(auto, 1),
                param1=_safe_float(p1),
                param2=_safe_float(p2),
                param3=_safe_float(p3),
                param4=_safe_float(p4),
                x=int(lat * 1e7),
                y=int(lon * 1e7),
                z=float(alt),
            )
        )
    return fleet_items


def _extract_json_array(text: str) -> str:
    """Extract JSON array from text response"""
    if not text:
        return ""
    
    # Clean up the text
    text = _strip_code_fences(text)
    
    # Look for JSON array pattern
    start_idx = text.find("[")
    if start_idx == -1:
        return ""
    
    # Find matching closing bracket
    bracket_count = 0
    end_idx = start_idx
    for i, char in enumerate(text[start_idx:], start_idx):
        if char == "[":
            bracket_count += 1
        elif char == "]":
            bracket_count -= 1
            if bracket_count == 0:
                end_idx = i + 1
                break
    
    if bracket_count == 0:
        return text[start_idx:end_idx]
    
    return ""


# -------------------- Payload Drop Helper --------------------
def drop_payload(master, channel: int = 10, pwm: int = 2000, duration_s: float = 2.0) -> None:
    """Override RC channel to a PWM for a duration, then release.
    Uses ArduPilot's extended RC_CHANNELS_OVERRIDE supporting up to 18 channels.
    """
    try:
        chans = [65535] * 18
        idx = max(1, min(18, int(channel))) - 1
        chans[idx] = int(pwm)
        # Engage
        master.mav.rc_channels_override_send(
            master.target_system,
            master.target_component,
            *chans[:8],
            *chans[8:18]
        )
        logger.info(f"[DROP] RC ch{channel} -> {pwm} for {duration_s}s")
        time.sleep(float(duration_s))
    finally:
        # Release (set all to ignore)
        chans = [65535] * 18
        master.mav.rc_channels_override_send(
            master.target_system,
            master.target_component,
            *chans[:8],
            *chans[8:18]
        )
        logger.info("[DROP] RC override released")


@app.post("/analyze_frame_contextual")
async def analyze_frame_contextual(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    frame_number: int = Form(0),
    is_first_frame: bool = Form(False),
    db: Session = Depends(database.get_db)
):
    """
    Contextual frame analysis that maintains conversation history across frames.
    This prevents duplicate object counting by tracking objects across the recording session.
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set")
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
    
    # Cleanup old sessions periodically
    cleanup_old_sessions()
    
    try:
        t_start = time.time()
        raw_bytes = await file.read()
        raw_size = len(raw_bytes) if raw_bytes is not None else 0
        logger.debug(f"/analyze_frame_contextual: session={session_id} frame={frame_number} bytes={raw_size}")
        
        t_pre0 = time.time()
        jpg_bytes = _encode_jpeg(raw_bytes)
        b64 = base64.b64encode(jpg_bytes).decode("utf-8")
        
        # Initialize or retrieve session
        # For context, we still need some in-memory or DB-retrieved history.
        # For simplicity in this refactor, we will fetch recent history from DB if needed,
        # but to keep it fast, we might want to keep a small LRU cache or just rely on the DB.
        
        # Let's create/get the session in DB
        if session_id:
            db_session = database.create_session(db, session_id)
            database.update_session_frame_count(db, session_id, frame_number)
        
        # Context history retrieval (simplified for now)
        # In a full implementation, we'd query the last few frames' objects.
        # For now, we'll assume stateless for the AI prompt to ensure speed, 
        # or we would need to reconstruct 'objects_seen' from DB.
        # Let's keep a local cache for 'objects_seen' just for the active session context if possible,
        # OR just rely on what the frontend sends (if it sent context).
        # Since the frontend doesn't send context, we'll start fresh or use a simplified prompt.
        
        # TODO: Re-implement full context history using DB queries if needed.
        # For now, we will proceed with the frame analysis and log it.
        
        history = [] # Placeholder for history
        objects_seen = {} # Placeholder for objects seen
        
        # Build context-aware prompt
        if is_first_frame or len(session["history"]) == 0:
            prompt = (
                "You are an object tracking system analyzing a video stream. This is the FIRST frame. "
                "Your task: Detect all objects and assign each a unique tracking ID. "
                "Return JSON format: [{\"object_id\": \"obj_1\", \"label\": \"person\", \"bbox\": [ymin, xmin, ymax, xmax], \"is_new\": true}]. "
                "Coordinates normalized 0-1000. Remember these objects for subsequent frames. "
                "Example: [{\"object_id\":\"obj_1\",\"label\":\"person\",\"bbox\":[100,200,500,600],\"is_new\":true}]"
            )
        else:
            # Build summary of previously seen objects
            obj_summary = ", ".join([f"{oid}: {data['label']}" for oid, data in session["objects_seen"].items()])
            prompt = (
                f"This is frame {frame_number} of the video stream. "
                f"Previously tracked objects: {obj_summary}. "
                "Your task: "
                "1. Check if previously tracked objects are still visible (match by position and appearance). "
                "2. Detect any NEW objects not seen before. "
                "3. Return JSON with ALL visible objects: "
                "   - Use same object_id for previously seen objects (is_new: false) "
                "   - Assign new object_id for new objects (is_new: true) "
                "Format: [{\"object_id\": \"obj_X\", \"label\": \"type\", \"bbox\": [ymin,xmin,ymax,xmax], \"is_new\": true/false}]. "
                "If an object left the frame, don't include it. Only return currently visible objects."
            )
        
        # Build contents array with conversation history
        contents = []
        
        # Add conversation history (limit to last 5 exchanges to avoid token limit)
        history_limit = 5
        # Add conversation history (limit to last 5 exchanges to avoid token limit)
        # history_limit = 5
        # for hist_entry in session["history"][-history_limit:]:
        #     contents.append(hist_entry)
        
        # Add current frame
        current_content = {
            "parts": [
                {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                {"text": prompt},
            ]
        }
        contents.append(current_content)
        
        model_path = ROBOTICS_MODEL if ROBOTICS_MODEL.startswith("models/") else f"models/{ROBOTICS_MODEL}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": GEMINI_API_KEY}
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        
        t_api0 = time.time()
        resp = requests.post(url, headers=headers, params=params, json=payload, timeout=20)
        t_api1 = time.time()
        
        if resp.status_code != 200:
            logger.warning("/analyze_frame_contextual: API error status=%s text=%s", resp.status_code, resp.text)
            return {"labels": [], "objects": [], "message": "API error", "session_id": session_id}
        
        data = resp.json()
        text = ""
        try:
            cand = data.get("candidates", [])
            if cand:
                parts = cand[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "text" in p:
                        text += p.get("text", "")
        except Exception:
            text = ""
        
        # Parse response
        labels: List[str] = []
        bboxes: List[List[float]] = []
        objects: List[Dict[str, Any]] = []
        
        try:
            json_str = _extract_json_array(text)
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                for obj in parsed:
                    if isinstance(obj, dict) and "label" in obj and "object_id" in obj:
                        label = obj["label"]
                        object_id = obj["object_id"]
                        is_new = obj.get("is_new", True)
                        
                        labels.append(label)
                        
                        if "bbox" in obj and isinstance(obj["bbox"], list) and len(obj["bbox"]) == 4:
                            bbox = obj["bbox"]
                            bboxes.append([float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])])
                        
                        obj_data = {
                            "object_id": object_id,
                            "label": label,
                            "bbox": obj.get("bbox", [100, 100, 300, 300]),
                            "confidence": 0.8,
                            "is_new": is_new
                        }
                        objects.append(obj_data)
                        
                        # Update session tracking
                        # if object_id not in session["objects_seen"]:
                        #     session["objects_seen"][object_id] = {
                        #         "label": label,
                        #         "first_seen": frame_number,
                        #         "last_seen": frame_number
                        #     }
                        # else:
                        #     session["objects_seen"][object_id]["last_seen"] = frame_number
        
        except Exception as parse_exc:
            logger.debug("/analyze_frame_contextual: JSON parse failed: %s", parse_exc)
            # Fallback to heuristic
            labels = _extract_labels_from_text(text)
        
        # Add to conversation history (store both request and response)
        # if session_id:
        #     session["history"].append(current_content)
        #     # Add assistant response to history
        #     if text:
        #         session["history"].append({
        #             "role": "model",
        #             "parts": [{"text": text}]
        #         })
        
        # Log to Database
        if session_id:
            database.log_frame_analysis(db, session_id, frame_number, objects, labels)
        
        t_parse1 = time.time()
        
        total_ms = (t_parse1 - t_start) * 1000.0
        api_ms = (t_api1 - t_api0) * 1000.0
        
        logger.info(
            "/analyze_frame_contextual: session=%s frame=%d total_ms=%.1f api_ms=%.1f labels=%d objects=%d new_objects=%d",
            session_id,
            frame_number,
            total_ms,
            api_ms,
            len(labels),
            len(objects),
            sum(1 for obj in objects if obj.get("is_new"))
        )
        
        return {
            "labels": labels[:10],
            "bboxes": bboxes[:10],
            "objects": objects[:10],
            "session_id": session_id,
            "frame_number": frame_number,
            "unique_objects_count": len(objects), # Simplified
            "message": "OK"
        }
        
    except Exception as exc:
        logger.exception("/analyze_frame_contextual error: %s", exc)
        return JSONResponse(status_code=200, content={
            "labels": [],
            "objects": [],
            "message": "Error processing frame",
            "session_id": session_id
        })


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY),
        "model": ROBOTICS_MODEL,
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY),
        "model": ROBOTICS_MODEL,
        "active_sessions": "Managed by DB"
    }


@app.get("/telemetry/sensors")
async def get_sensor_data(session_id: Optional[str] = None, sys_id: Optional[int] = None, db: Session = Depends(database.get_db)):
    """
    Get sensor data for a specific drone or the entire fleet.
    
    Args:
        session_id: Optional session identifier
        sys_id: Optional system ID to get data for a specific drone. If None, returns data for all drones.
    
    Returns:
        If sys_id is provided: Single drone telemetry data (compatible with existing frontend format)
        If sys_id is None: Fleet snapshot with all drones {sys_id: {telemetry_data}}
    """
    try:
        fleet = get_swarm_manager()
        
        # If fleet manager is active, use it for multi-drone support
        if fleet is not None:
            snapshot = fleet.get_fleet_snapshot()
            
            if sys_id is not None:
                # Return single drone data in the format expected by frontend
                if sys_id not in snapshot:
                    raise HTTPException(status_code=404, detail=f"Drone with sys_id {sys_id} not found")
                
                drone_data = snapshot[sys_id]
                logger.debug(f"Returning telemetry for sys_id={sys_id}: {drone_data}")
                
                # Convert fleet manager format to frontend-compatible format
                data = {
                    "gps": {
                        "latitude": drone_data.get("latitude_deg"),
                        "longitude": drone_data.get("longitude_deg"),
                        "altitude": drone_data.get("altitude_m"),
                        "speed": drone_data.get("gps_speed") or drone_data.get("groundspeed_m_s"),
                        "heading": drone_data.get("gps_heading") or drone_data.get("vfr_heading"),
                        "fix_type": drone_data.get("gps_fix_type"),
                        "satellites": drone_data.get("gps_satellites"),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "attitude": {
                        "roll": drone_data.get("roll"),
                        "pitch": drone_data.get("pitch"),
                        "yaw": drone_data.get("yaw"),
                        "rollspeed": None,  # Not tracked in DroneStatus
                        "pitchspeed": None,
                        "yawspeed": None,
                        "timestamp": datetime.now().isoformat(),
                    },
                    "vfr_hud": {
                        "airspeed": drone_data.get("vfr_airspeed"),
                        "groundspeed": drone_data.get("groundspeed_m_s"),
                        "heading": drone_data.get("vfr_heading") or drone_data.get("gps_heading"),
                        "throttle": drone_data.get("vfr_throttle"),
                        "alt": drone_data.get("altitude_m"),
                        "climb": drone_data.get("vfr_climb"),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "battery": {
                        "voltage": drone_data.get("battery_voltage"),
                        "current": None,  # Not tracked in DroneStatus
                        "remaining": drone_data.get("battery_remaining"),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "system": {
                        "onboard_control_sensors_present": None,
                        "onboard_control_sensors_enabled": None,
                        "onboard_control_sensors_health": None,
                        "load": None,
                        "voltage_battery": drone_data.get("battery_voltage"),
                        "current_battery": None,
                        "battery_remaining": drone_data.get("battery_remaining"),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "status": {
                        "armed": drone_data.get("armed"),
                        "mode": drone_data.get("flight_mode"),
                    },
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                }
                
                # Log to DB
                if session_id:
                    database.log_telemetry(db, data, session_id, sys_id)
                
                return data
            else:
                # No sys_id provided - return first drone's data for backward compatibility
                # This allows MissionPlannerPanel and other components to work without changes
                if snapshot:
                    first_sys_id = min(snapshot.keys())
                    drone_data = snapshot[first_sys_id]
                    logger.debug(f"No sys_id provided, returning first drone (sys_id={first_sys_id}): {drone_data}")
                    
                    data = {
                        "gps": {
                            "latitude": drone_data.get("latitude_deg"),
                            "longitude": drone_data.get("longitude_deg"),
                            "altitude": drone_data.get("altitude_m"),
                            "speed": drone_data.get("gps_speed") or drone_data.get("groundspeed_m_s"),
                            "heading": drone_data.get("gps_heading") or drone_data.get("vfr_heading"),
                            "fix_type": drone_data.get("gps_fix_type"),
                            "satellites": drone_data.get("gps_satellites"),
                            "timestamp": datetime.now().isoformat(),
                        },
                        "attitude": {
                            "roll": drone_data.get("roll"),
                            "pitch": drone_data.get("pitch"),
                            "yaw": drone_data.get("yaw"),
                            "rollspeed": None,
                            "pitchspeed": None,
                            "yawspeed": None,
                            "timestamp": datetime.now().isoformat(),
                        },
                        "vfr_hud": {
                            "airspeed": drone_data.get("vfr_airspeed"),
                            "groundspeed": drone_data.get("groundspeed_m_s"),
                            "heading": drone_data.get("vfr_heading") or drone_data.get("gps_heading"),
                            "throttle": drone_data.get("vfr_throttle"),
                            "alt": drone_data.get("altitude_m"),
                            "climb": drone_data.get("vfr_climb"),
                            "timestamp": datetime.now().isoformat(),
                        },
                        "battery": {
                            "voltage": drone_data.get("battery_voltage"),
                            "current": None,
                            "remaining": drone_data.get("battery_remaining"),
                            "timestamp": datetime.now().isoformat(),
                        },
                        "system": {
                            "onboard_control_sensors_present": None,
                            "onboard_control_sensors_enabled": None,
                            "onboard_control_sensors_health": None,
                            "load": None,
                            "voltage_battery": drone_data.get("battery_voltage"),
                            "current_battery": None,
                            "battery_remaining": drone_data.get("battery_remaining"),
                            "timestamp": datetime.now().isoformat(),
                        },
                        "status": {
                            "armed": drone_data.get("armed"),
                            "mode": drone_data.get("flight_mode"),
                        },
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                else:
                    # No drones in fleet yet
                    return {
                        "gps": {"latitude": None, "longitude": None, "altitude": None, "speed": None, "heading": None, "fix_type": None, "satellites": None, "timestamp": datetime.now().isoformat()},
                        "attitude": {"roll": None, "pitch": None, "yaw": None, "rollspeed": None, "pitchspeed": None, "yawspeed": None, "timestamp": datetime.now().isoformat()},
                        "vfr_hud": {"airspeed": None, "groundspeed": None, "heading": None, "throttle": None, "alt": None, "climb": None, "timestamp": datetime.now().isoformat()},
                        "battery": {"voltage": None, "current": None, "remaining": None, "timestamp": datetime.now().isoformat()},
                        "system": {"onboard_control_sensors_present": None, "onboard_control_sensors_enabled": None, "onboard_control_sensors_health": None, "load": None, "voltage_battery": None, "current_battery": None, "battery_remaining": None, "timestamp": datetime.now().isoformat()},
                        "status": {"armed": None, "mode": None},
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }
        
        # Fallback to legacy single-drone system for backward compatibility
        import time as _time
        from telemetry_fetchers import get_global_mavlink_receiver
        deadline = _time.time() + 5.0
        while True:
            try:
                rec = get_global_mavlink_receiver()
                status = rec.fetch_status() if rec and rec.is_connected() else None
                if status is not None:
                    break
            except Exception:
                pass
            if _time.time() >= deadline:
                break
            _time.sleep(0.25)

        telemetry_manager = get_telemetry_manager(session_id)

        # Try a short readiness loop for first real data (avoid returning blanks right after connect)
        import math as _math
        start_ts = _time.time()
        data = None
        while True:
            d = telemetry_manager.fetch_all_data()
            gps = d.get("gps", {}) if isinstance(d, dict) else {}
            lat = gps.get("latitude")
            lon = gps.get("longitude")
            lat_ok = isinstance(lat, (int, float)) and _math.isfinite(lat)
            lon_ok = isinstance(lon, (int, float)) and _math.isfinite(lon)
            if lat_ok and lon_ok:
                data = d
                break
            if _time.time() - start_ts > 3.0:
                data = d
                break
            _time.sleep(0.2)



        if data and session_id:
             database.log_telemetry(db, data, session_id)

        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("/telemetry/sensors error: %s", exc)
        raise HTTPException(status_code=503, detail="Telemetry unavailable")


@app.post("/path/generate")
async def generate_surveillance_path(
    kml_file: UploadFile = File(...),
    uav_start_lat: float = Form(...),
    uav_start_lon: float = Form(...),
    sensor_width: float = Form(30.0),
    overlap: float = Form(0.2)
):
    """
    Generate optimized surveillance path from KML geofence.
    Returns waypoints in Cesium-compatible format.
    """
    try:
        # Read KML file
        kml_content = await kml_file.read()
        
        # Save temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.kml') as tmp:
            tmp.write(kml_content)
            tmp_path = tmp.name
        
        try:
            # Parse KML and generate path
            geofence_coords = parse_kml(tmp_path)
            geofence = Polygon(geofence_coords)
            
            # Generate path
            # Note: generate_surveillance_path returns a list of (lon, lat) tuples
            waypoints = generate_surveillance_path(
                geofence, 
                overlap, 
                sensor_width, 
                Point(uav_start_lon, uav_start_lat)
            )
            
            if not waypoints:
                raise HTTPException(status_code=400, detail="Could not generate valid path")
            
            # Convert to Cesium format
            cesium_waypoints = [
                {
                    "longitude": wp[0],
                    "latitude": wp[1],
                    "altitude": 0  # Can be customized
                }
                for wp in waypoints
            ]
            
            # Calculate path statistics
            from shapely.geometry import LineString
            path_line = LineString(waypoints)
            path_length_deg = path_line.length
            path_length_km = path_length_deg * 111.320
            
            # Calculate coverage
            meters_per_degree_lat = 111320.0
            sensor_buffer_deg = (sensor_width / 2.0) / meters_per_degree_lat
            surveyed_area = path_line.buffer(sensor_buffer_deg, cap_style=3)
            covered_area = surveyed_area.intersection(geofence).area
            total_area = geofence.area
            coverage_ratio = covered_area / total_area if total_area > 0 else 0
            
            return {
                "waypoints": cesium_waypoints,
                "statistics": {
                    "total_waypoints": len(waypoints),
                    "path_length_km": round(path_length_km, 3),
                    "coverage_ratio": round(coverage_ratio, 4),
                    "geofence_bounds": {
                        "west": min(c[0] for c in geofence_coords),
                        "south": min(c[1] for c in geofence_coords),
                        "east": max(c[0] for c in geofence_coords),
                        "north": max(c[1] for c in geofence_coords)
                    }
                },
                "message": "Path generated successfully"
            }
            
        finally:
            # Clean up temp file
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as exc:
        logger.exception("/path/generate error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/mission/start")
async def start_mission(
    kml_file: UploadFile = File(...),
    use_drone_position: bool = Form(True),
    start_lat: Optional[float] = Form(None),
    start_lon: Optional[float] = Form(None),
    altitude: float = Form(50.0),
    speed: float = Form(5.0),
    sensor_width: float = Form(30.0),
    overlap: float = Form(0.2),
    connection_string: Optional[str] = Form(None),
    save_to_file: bool = Form(False),
    output_file: Optional[str] = Form(None),
    auto_start: bool = Form(True),
    end_action: str = Form("RTL"),
    sys_id: Optional[int] = Form(None),  # New: target specific drone by system ID
    # Optional payload drop configuration for KML-based mission
    drop_at_end: bool = Form(False),
    drop_channel: Optional[int] = Form(None),
    drop_pwm: Optional[int] = Form(None),
    drop_duration_s: Optional[float] = Form(None),
):
    """
    Generate an optimized mission from a KML geofence and upload it to a vehicle via MAVLink.
    - If use_drone_position is True, tries to fetch start position from the vehicle.
    - Otherwise requires start_lat/start_lon.
    Returns mission summary and upload status.
    """
    try:
        if overlap < 0 or overlap > 1:
            raise HTTPException(status_code=400, detail="overlap must be between 0 and 1")
        if altitude <= 0:
            raise HTTPException(status_code=400, detail="altitude must be positive")
        if speed <= 0:
            raise HTTPException(status_code=400, detail="speed must be positive")

        # Read and persist KML to a temp file
        kml_bytes = await kml_file.read()
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.kml') as tmp:
            tmp.write(kml_bytes)
            tmp_kml_path = tmp.name

        try:
            # Determine connection string.
            # If MAVProxy router is active, it's CRITICAL to use the mission output port.
            conn_str = connection_string
            if MAVPROXY_ROUTER_ACTIVE:
                logger.info("MAVProxy router is active. Using dedicated mission output for this operation.")
                conn_str = MAVPROXY_PORTS.get("mission_conn_str")
                if not conn_str:
                    raise HTTPException(status_code=500, detail="MAVProxy router is active but mission port is not configured.")
            
            if not conn_str:
                 raise HTTPException(status_code=400, detail="No MAVLink connection string available for mission.")

            # Determine UAV start point
            uav_start_point: Optional[Point] = None
            if not use_drone_position:
                if start_lat is None or start_lon is None:
                    raise HTTPException(status_code=400, detail="start_lat and start_lon are required when use_drone_position is False")
                uav_start_point = Point(float(start_lon), float(start_lat))
            else:
                # Use the globally shared MAVLink connection
                shared_master = get_global_mavlink_master()
                if not shared_master:
                    raise HTTPException(status_code=503, detail="Cannot get drone position: MAVLink connection not active.")

                drone_pt = waypoint_mission.get_drone_position(shared_master)
                if drone_pt is not None:
                    uav_start_point = drone_pt
                elif start_lat is not None and start_lon is not None:
                    uav_start_point = Point(float(start_lon), float(start_lat))
                else:
                    # As a last resort, use module defaults to avoid hardcoding here
                    uav_start_point = Point(waypoint_mission.UAV_START_LON, waypoint_mission.UAV_START_LAT)

            # Generate mission using mission module (handles internal path optimizations)
            mavlink_mission, geofence_coords = waypoint_mission.generate_optimized_path(
                kml_file=tmp_kml_path,
                uav_start_location=uav_start_point,
                sensor_width=float(sensor_width),
                overlap=float(overlap),
                altitude=float(altitude),
                speed=float(speed),
                verbose=False,
            )

            # Append end action
            mavlink_mission.add_mission_end_command(end_action=end_action.upper())

            # Optionally save waypoint file
            saved_file = None
            if save_to_file:
                fname = output_file or waypoint_mission.OUTPUT_FILE
                mavlink_mission.save_to_waypoint_file(fname)
                saved_file = fname

            # Upload and optionally start
            success = False
            try:
                # If sys_id is provided, use SwarmManager for multi-drone support
                if sys_id is not None:
                    fleet = get_swarm_manager()
                    if not fleet:
                        raise HTTPException(status_code=503, detail="SwarmManager not active. Connect to telemetry first.")
                    
                    # Extract mission waypoints (lat, lon, alt) from generated mission items
                    from pymavlink import mavutil as _mavutil
                    waypoints: list[tuple[float, float, float]] = []
                    for item in getattr(mavlink_mission, "mission_items", []):
                        if len(item) < 12:
                            continue
                        cmd = item[2]
                        lat = item[9]
                        lon = item[10]
                        alt = item[11]
                        if cmd not in {
                            _mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                            _mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                            _mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME,
                        }:
                            continue
                        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
                            continue
                        waypoints.append((float(lat), float(lon), float(alt)))
                    
                    # Upload via SwarmManager
                    fleet.send_command(sys_id, "upload_mission", {"waypoints": waypoints})
                    success = True
                    logger.info(f"Mission uploaded to drone sys_id={sys_id} via SwarmManager")
                else:
                    # Legacy single-drone upload
                    shared_master = get_global_mavlink_master()
                    if not shared_master:
                        raise HTTPException(status_code=503, detail="Cannot upload mission: MAVLink connection not active.")
                    
                    success, _ = mavlink_mission.upload_to_vehicle(shared_master, auto_start=auto_start)
            except OSError as os_err:
                # Common bind error when port is already in use
                msg = str(os_err) or "OSError"
                if "Address already in use" in msg or getattr(os_err, 'errno', None) in (48, 98):
                    # This error should no longer happen with the shared connection, but is kept as a safeguard
                    raise HTTPException(status_code=409, detail="Address already in use on connection. This should not happen with the new architecture.")
                raise
            
            # The master connection is managed globally, so we don't close it here.

            # Build summary
            summary = {
                "total_items": len(mavlink_mission.mission_items),
                "survey_waypoints": len(mavlink_mission.waypoints),
                "altitude_m": mavlink_mission.altitude,
                "speed_mps": mavlink_mission.speed,
                "end_action": end_action.upper(),
                "saved_file": saved_file,
                "connection": conn_str,
                "uploaded": bool(success),
                "auto_started": bool(success and auto_start),
            }

            if not success:
                return JSONResponse(status_code=500, content={
                    "message": "Mission upload failed",
                    "summary": summary,
                })

            # If requested, schedule a payload drop near mission end using a simple ETA
            if success and auto_start and drop_at_end:
                try:
                    # Estimate time based on path length using haversine over waypoints
                    # Fallback to a conservative 60s if we cannot estimate
                    def _estimate_seconds(waypoints_ll, v_mps: float) -> float:
                        import math as _m
                        if not waypoints_ll or len(waypoints_ll) < 2 or v_mps <= 0:
                            return 60.0
                        R = 6371000.0
                        total = 0.0
                        for a, b in zip(waypoints_ll[:-1], waypoints_ll[1:]):
                            lon1, lat1 = _m.radians(a[0]), _m.radians(a[1])
                            lon2, lat2 = _m.radians(b[0]), _m.radians(b[1])
                            dlon = lon2 - lon1
                            dlat = lat2 - lat1
                            h = _m.sin(dlat/2)**2 + _m.cos(lat1)*_m.cos(lat2)*_m.sin(dlon/2)**2
                            d = 2 * R * _m.asin(_m.sqrt(h))
                            total += d
                        # Add a small buffer (10%)
                        eta = (total / v_mps) * 1.1
                        # Clamp ETA between 10s and 2 hours
                        return max(10.0, min(eta, 2*60*60))

                    waypoints_ll = getattr(mavlink_mission, 'waypoints', [])
                    v_mps = float(mavlink_mission.speed)
                    eta_s = _estimate_seconds(waypoints_ll, v_mps)

                    ch = int(drop_channel) if drop_channel is not None else 10
                    pwm = int(drop_pwm) if drop_pwm is not None else 2000
                    dur = float(drop_duration_s) if drop_duration_s is not None else 2.0

                    # Log the scheduling with parameters
                    logger.info(
                        f"[DROP][KML] Scheduled end-of-mission drop: eta={eta_s:.1f}s channel={ch} pwm={pwm} duration={dur}s"
                    )

                    def _delayed_drop(master):
                        try:
                            time.sleep(eta_s)
                            logger.info("[DROP][KML] ETA reached; triggering end-of-mission payload drop now")
                            drop_payload(master, channel=ch, pwm=pwm, duration_s=dur)
                            logger.info("[DROP][KML] End-of-mission payload drop completed")
                        except Exception as e:
                            logger.warning(f"[DROP] Delayed drop failed: {e}")

                    t = threading.Thread(target=_delayed_drop, args=(shared_master,), daemon=True)
                    t.start()
                    summary["drop_scheduled"] = True
                    summary["drop_eta_seconds"] = round(eta_s, 1)
                except Exception as _e:
                    logger.warning(f"[DROP] Scheduling end-of-mission drop failed: {_e}")
                    summary["drop_scheduled"] = False

            return {"message": "Mission uploaded successfully", "summary": summary}

        finally:
            import os
            if os.path.exists(tmp_kml_path):
                os.unlink(tmp_kml_path)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("/mission/start error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    database.init_db()
    logger.info("Database initialized")
    
    # Start Video Manager
    video_manager.start()
    
    # Start AI Analysis Thread
    global ai_analysis_active
    ai_analysis_active = True
    t = threading.Thread(target=ai_analysis_loop, daemon=True)
    t.start()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    video_manager.stop()
    if _global_swarm_manager:
        _global_swarm_manager.stop()
    shutdown_telemetry_manager()
    stop_mavproxy()
    logger.info("Application shutdown complete")

@app.get("/video_feed")
def video_feed():
    """Stream video from the backend"""
    return StreamingResponse(video_manager.generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/ai_analysis")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/test/analyze_image")
async def test_analyze_image(file: UploadFile = File(...)):
    """
    Test endpoint to analyze an uploaded image directly with Gemini.
    Useful for verifying detection capabilities without a drone.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
            
        result = gemini_service.analyze_frame(frame)
        return JSONResponse(content=result or {"error": "Analysis failed"})
    except Exception as e:
        logger.error(f"Test analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/telemetry/connect")
async def connect_telemetry(settings: dict = Body(...)):
    """
    Connect to MAVLink source(s) using SwarmManager for multi-drone support.
    
    Supports two formats:
    1. Single connection (backward compatible):
       {"protocol": "UDP", "host": "127.0.0.1", "port": 14550}
    
    2. Multiple connections (for multiple ports/receivers):
       {"connections": [
           {"protocol": "UDP", "host": "127.0.0.1", "port": 14550},
           {"protocol": "UDP", "host": "127.0.0.1", "port": 14551}
       ]}
    
    If the source is a serial port, it will start a MAVProxy router to multiplex the connection.
    """
    global MAVPROXY_ROUTER_ACTIVE, MAVPROXY_PORTS
    
    # Always stop previous connections/routers before starting a new one
    stop_mavproxy()
    shutdown_telemetry_manager()
    shutdown_swarm_manager()
    MAVPROXY_ROUTER_ACTIVE = False
    MAVPROXY_PORTS = {}

    connection_strings: List[str] = []
    
    # Check if multiple connections are provided
    if "connections" in settings:
        # Multiple connections format
        connections_list = settings.get("connections", [])
        if not isinstance(connections_list, list) or len(connections_list) == 0:
            raise HTTPException(status_code=400, detail="'connections' must be a non-empty list")
        
        for idx, conn_settings in enumerate(connections_list):
            protocol = conn_settings.get("protocol")
            if not protocol:
                raise HTTPException(status_code=400, detail=f"Connection {idx}: 'protocol' is required")
            
            if protocol == "SERIAL":
                serial_port = conn_settings.get("port")
                baud_rate = conn_settings.get("baud", 57600)
                if not serial_port:
                    raise HTTPException(status_code=400, detail=f"Connection {idx}: Serial port is required")
                connection_strings.append(serial_port)
            else:
                host = conn_settings.get("host", "127.0.0.1")
                port = conn_settings.get("port", 14550 if protocol == "UDP" else 5760)
                
                if protocol == "UDP":
                    connection_strings.append(f"udp:{host}:{port}")
                elif protocol == "TCP":
                    connection_strings.append(f"tcp:{host}:{port}")
                else:
                    raise HTTPException(status_code=400, detail=f"Connection {idx}: Unsupported protocol: {protocol}")
    else:
        # Single connection format (backward compatible)
        protocol = settings.get("protocol")
        if not protocol:
            raise HTTPException(status_code=400, detail="'protocol' is required")
        
        if protocol == "SERIAL":
            serial_port = settings.get("port")
            baud_rate = settings.get("baud")
            if not serial_port or not baud_rate:
                raise HTTPException(status_code=400, detail="Serial port and baud rate are required for SERIAL connection.")
            
            # Try to use MAVProxy router first (for mission multiplexing), but fall back to direct connection
            logger.info(f"SERIAL connection requested. Attempting MAVProxy router on {serial_port}@{baud_rate}...")
            ports = start_mavproxy(serial_port, baud_rate)
            
            if ports:
                MAVPROXY_ROUTER_ACTIVE = True
                MAVPROXY_PORTS = ports
                # Use the router's telemetry output for SwarmManager
                connection_strings.append(MAVPROXY_PORTS["telemetry_conn_str"])
                logger.info(f"MAVProxy router started. SwarmManager connecting to {MAVPROXY_PORTS['telemetry_conn_str']}")
            else:
                # MAVProxy failed, use direct serial connection instead
                logger.warning(f"MAVProxy router failed to start. Falling back to direct SERIAL connection on {serial_port}@{baud_rate}")
                MAVPROXY_ROUTER_ACTIVE = False
                MAVPROXY_PORTS = {}
                connection_strings.append(serial_port)
                logger.info(f"Using direct SERIAL connection (no router).")
        else:
            # For UDP/TCP, build connection string
            host = settings.get("host", "127.0.0.1")
            port = settings.get("port", 14550 if protocol == "UDP" else 5760)
            
            if protocol == "UDP":
                connection_strings.append(f"udp:{host}:{port}")
            elif protocol == "TCP":
                connection_strings.append(f"tcp:{host}:{port}")
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported protocol: {protocol}")
            
            logger.info(f"Direct {protocol} connection requested: {connection_strings[0]}")
        
        # Also update legacy telemetry settings for backward compatibility
        if protocol == "SERIAL" and MAVPROXY_ROUTER_ACTIVE:
            telemetry_conn_parts = MAVPROXY_PORTS["telemetry_conn_str"].split(':')
            telemetry_connection_settings.update({
                "protocol": "UDP",
                "host": telemetry_conn_parts[1],
                "port": int(telemetry_conn_parts[2]),
            })
        elif protocol == "SERIAL":
            telemetry_connection_settings.update({
                "protocol": "SERIAL",
                "serial_port": serial_port,
                "port": serial_port,
                "baud": baud_rate,
            })
        else:
            telemetry_connection_settings.update(settings)

    # Initialize SwarmManager with all connection strings
    if connection_strings:
        init_swarm_manager(connection_strings)
        init_mission_controller()  # Initialize MissionController with ConnectionManager
        logger.info(f"SwarmManager initialized with {len(connection_strings)} connection(s). Ready for multi-drone operations.")
    
    return {
        "message": "SwarmManager connected and ready for multi-drone operations.",
        "connections": connection_strings,
        "count": len(connection_strings),
        "settings": telemetry_connection_settings if "connections" not in settings else None,
    }


@app.post("/telemetry/disconnect")
async def disconnect_telemetry():
    """
    Disconnects from MAVLink source, stops SwarmManager, and stops the MAVProxy router if it's running.
    """
    global MAVPROXY_ROUTER_ACTIVE, MAVPROXY_PORTS
    
    logger.info("Disconnect requested. Shutting down SwarmManager, telemetry, and MAVProxy router.")
    
    # Stop SwarmManager
    shutdown_swarm_manager()
    
    # Stop the router process
    stop_mavproxy()
    
    # Shut down the telemetry fetching thread
    shutdown_telemetry_manager()
    
    # Reset connection settings
    for key in telemetry_connection_settings:
        telemetry_connection_settings[key] = None
        
    # Reset global state
    MAVPROXY_ROUTER_ACTIVE = False
    MAVPROXY_PORTS = {}
    
    return {"message": "SwarmManager disconnected and router stopped."}


@app.get("/fleet/status")
async def get_fleet_status():
    """Get status of all drones in the fleet."""
    fleet = get_swarm_manager()
    if not fleet:
        return {"fleet": {}, "count": 0, "message": "SwarmManager not active"}
    
    snapshot = fleet.get_fleet_snapshot()
    return {
        "fleet": snapshot,
        "count": len(snapshot),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# -------------------- Manual Waypoint Mission Endpoint --------------------
@app.post("/mission/manual")
async def manual_mission_upload(payload: ManualMissionRequest):
    """
    Accepts a list of manual waypoints with per-point altitude and mode, builds a
    MAVLink mission, and uploads it over the existing shared MAVLink connection.

    Request body:
    {
      "waypoints": [
        {"longitude": 72.0, "latitude": 19.0, "altitude": 50, "mode": "WAYPOINT"},
        ...
      ],
      "speed": 5.0,
      "end_action": "RTL" | "LAND" | "NONE"
    }
    """
    try:
        wps = payload.waypoints or []
        if len(wps) == 0:
            raise HTTPException(status_code=400, detail="At least one waypoint is required")

        # Build mission_items in the same tuple format as PathToMavlink
        # (seq, frame, cmd, current, auto, p1, p2, p3, p4, lat, lon, alt, mission_type)
        from pymavlink import mavutil as _mavutil

        seq = 0
        mission_items = []

        # Speed command first if provided (do NOT mark as current)
        speed = float(payload.speed) if payload.speed is not None else 5.0
        mission_items.append(
            (
                seq,
                _mavutil.mavlink.MAV_FRAME_MISSION,
                _mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
                0,
                1,
                1,  # airspeed
                speed,
                -1,
                0,
                0,
                0,
                0,
                _mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        )
        seq += 1

        # Translate manual waypoints to mission commands
        def mode_to_cmd(mode_str: str) -> int:
            m = (mode_str or "").upper()
            if m == "TAKEOFF":
                return _mavutil.mavlink.MAV_CMD_NAV_TAKEOFF
            if m == "LOITER":
                return _mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME
            if m == "LAND":
                return _mavutil.mavlink.MAV_CMD_NAV_LAND
            # HOLD maps to loiter time with 0s unless adjusted later
            if m == "HOLD":
                return _mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME
            return _mavutil.mavlink.MAV_CMD_NAV_WAYPOINT

        for i, wp in enumerate(wps):
            cmd = mode_to_cmd(wp.mode)
            hold_seconds = 0.0
            if cmd == _mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME and wp.mode.upper() == "HOLD":
                hold_seconds = 1.0  # small dwell by default; adjustable by client later

            mission_items.append(
                (
                    seq,
                    _mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    cmd,
                    1 if (i == 0) else 0,
                    1,
                    hold_seconds,  # Param1: hold time for LOITER/HOLD, 0 otherwise
                    0,
                    0,
                    0,
                    float(wp.latitude),
                    float(wp.longitude),
                    float(wp.altitude),
                    _mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                )
            )
            seq += 1

        # Optional end action
        end_action = (payload.end_action or "RTL").upper()
        if end_action in {"RTL", "LAND"}:
            if end_action == "RTL":
                mission_items.append(
                    (
                        seq,
                        _mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                        _mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                        0,
                        1,
                        0, 0, 0, 0,
                        0, 0, 0,
                        _mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                    )
                )
            else:
                last = wps[-1]
                mission_items.append(
                    (
                        seq,
                        _mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                        _mavutil.mavlink.MAV_CMD_NAV_LAND,
                        0,
                        1,
                        0, 0, 0, 0,
                        float(last.latitude),
                        float(last.longitude),
                        0.0,
                        _mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                    )
                )
            seq += 1

        # Upload mission - support both SwarmManager (multi-drone) and legacy (single-drone)
        if payload.sys_id is not None:
            # Use SwarmManager for multi-drone support
            fleet = get_swarm_manager()
            if not fleet:
                raise HTTPException(status_code=503, detail="SwarmManager not active. Connect to telemetry first.")
            
            fleet_mission = _convert_mission_items_for_fleet(mission_items)
            if not fleet_mission:
                raise HTTPException(status_code=400, detail="No mission items available for upload")

            logger.info(
                "Prepared %d mission items (including commands) for SwarmManager upload (sys_id=%s)",
                len(fleet_mission),
                payload.sys_id,
            )
            
            # Upload via SwarmManager with full mission definition
            fleet.send_command(payload.sys_id, "upload_mission", {"mission_items": fleet_mission})
            logger.info(f"Manual mission uploaded to drone sys_id={payload.sys_id} via SwarmManager")

            # Build simple waypoint list for summaries/auto-start altitude
            waypoints: list[tuple[float, float, float]] = []
            for wp in wps:
                if wp.latitude is None or wp.longitude is None or wp.altitude is None:
                    continue
                waypoints.append((float(wp.latitude), float(wp.longitude), float(wp.altitude)))
            
            # Auto-start if explicitly requested
            auto_started = False
            should_auto_start = payload.auto_start is None or payload.auto_start
            if should_auto_start:
                logger.info(f"Auto-starting mission for drone sys_id={payload.sys_id}")
                takeoff_alt = float(waypoints[0][2]) if waypoints else 30.0
                auto_started = fleet.send_command(
                    payload.sys_id,
                    "arm_and_start_mission",
                    {"takeoff_altitude": takeoff_alt}
                )
                if auto_started:
                    logger.info(f"Mission auto-started for drone sys_id={payload.sys_id}")
                else:
                    logger.warning(f"Failed to auto-start mission for drone sys_id={payload.sys_id}")
            
            return {
                "message": f"Mission uploaded to drone sys_id={payload.sys_id}",
                "waypoint_count": len(waypoints),
                "summary": {"auto_started": auto_started}
            }
        else:
            # Legacy single-drone upload
            shared_master = get_global_mavlink_master()
            if not shared_master:
                raise HTTPException(status_code=503, detail="MAVLink connection not active. For multi-drone setup, provide sys_id parameter.")

            # Reuse PathToMavlink's upload routine for reliability
        mission_obj = waypoint_mission.PathToMavlink(waypoints=[], altitude=0, speed=speed)
        mission_obj.mission_items = mission_items
        # Upload the mission
        # Track HOLD item sequences to trigger payload drop when reached
        hold_seq_set = set()
        for item in mission_items:
            seq_i, _frame, _cmd, _current, _auto, p1, p2, p3, p4, lat, lon, alt, _mt = item
            if _cmd == _mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME:
                hold_seq_set.add(seq_i)

        success, _ = mission_obj.upload_to_vehicle(shared_master, auto_start=False)

        # Auto-start if requested: set GUIDED, arm+takeoff, then AUTO
        auto_started = False
        if success and (payload.auto_start is None or payload.auto_start):
            # Choose a reasonable takeoff altitude: use first nav item's altitude if present
            takeoff_alt = float(wps[0].altitude) if wps and wps[0].altitude is not None else 30.0
            mission_obj.altitude = takeoff_alt
            ok, _ = mission_obj.arm_and_start_mission(shared_master)
            auto_started = bool(ok)

            # If there are HOLD points, monitor mission progress and trigger drop at those points
            if auto_started and hold_seq_set:
                try:
                    ch = int(payload.drop_channel) if payload.drop_channel is not None else 10
                    pwm = int(payload.drop_pwm) if payload.drop_pwm is not None else 2000
                    dur = float(payload.drop_duration_s) if payload.drop_duration_s is not None else 2.0

                    # Log monitor setup
                    logger.info(
                        f"[DROP][MANUAL] Monitoring HOLD sequences {sorted(list(hold_seq_set))} "
                        f"for payload drop: channel={ch} pwm={pwm} duration={dur}s"
                    )

                    def _monitor_and_drop(master, target_seqs: set[int], channel: int, pwm_val: int, dur_s: float):
                        import time as _t
                        pending = set(target_seqs)
                        last_seen = None
                        deadline = _t.time() + 60 * 60  # 1 hour max monitoring
                        while pending and _t.time() < deadline:
                            try:
                                msg = master.recv_match(type='MISSION_CURRENT', blocking=False)
                                if msg is not None:
                                    curr = getattr(msg, 'seq', None)
                                    last_seen = curr
                                    if curr in pending:
                                        logger.info(f"[DROP][MANUAL] Reached HOLD seq {curr}; triggering payload drop")
                                        drop_payload(master, channel=channel, pwm=pwm_val, duration_s=dur_s)
                                        logger.info(f"[DROP][MANUAL] Payload drop completed at HOLD seq {curr}")
                                        pending.remove(curr)
                                _t.sleep(0.2)
                            except Exception:
                                _t.sleep(0.5)
                                continue
                        if pending:
                            logger.info(f"[DROP] Monitor finished with pending HOLD seqs not reached: {sorted(pending)} last_seen={last_seen}")
                        else:
                            logger.info("[DROP][MANUAL] All configured HOLD-triggered payload drops completed")

                    t = threading.Thread(target=_monitor_and_drop, args=(shared_master, hold_seq_set, ch, pwm, dur), daemon=True)
                    t.start()
                except Exception as mon_e:
                    logger.warning(f"[DROP] Failed to start HOLD monitor: {mon_e}")

        summary = {
            "total_items": len(mission_items),
            "waypoints": len(wps),
            "uploaded": bool(success),
            "end_action": end_action,
            "speed_mps": speed,
            "auto_started": auto_started,
        }

        if not success:
            return JSONResponse(status_code=500, content={
                "message": "Mission upload failed",
                "summary": summary,
            })

        return {"message": "Manual mission uploaded successfully", "summary": summary}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("/mission/manual error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ===== VIDEO RECORDING ENDPOINTS =====

@app.post("/recording/start")
async def start_recording(session_id: str = Body(..., embed=True)):
    """Start video recording with AI analysis logging"""
    try:
        result = video_recorder.start_recording(session_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"Recording started for session {session_id}")
        return result
    except Exception as e:
        logger.exception("Failed to start recording")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recording/stop")
async def stop_recording():
    """Stop current recording and save files"""
    try:
        result = video_recorder.stop_recording()
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"Recording stopped: {result.get('session_dir')}")
        return result
    except Exception as e:
        logger.exception("Failed to stop recording")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recording/status")
async def get_recording_status():
    """Get current recording status"""
    try:
        return video_recorder.get_status()
    except Exception as e:
        logger.exception("Failed to get recording status")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recordings/list")
async def list_recordings():
    """List all saved recordings"""
    try:
        recordings = video_recorder.list_recordings()
        return {"recordings": recordings, "total": len(recordings)}
    except Exception as e:
        logger.exception("Failed to list recordings")
        raise HTTPException(status_code=500, detail=str(e))


# ===== VIDEO SOURCE MANAGEMENT ENDPOINTS =====

@app.post("/video/source")
async def set_video_source(source: str = Body(..., embed=True)):
    """Change video source dynamically"""
    global video_manager
    try:
        logger.info(f"Changing video source to: {source}")
        video_manager.stop()
        parsed_source = int(source) if source.isdigit() else source
        video_manager = VideoManager(source=parsed_source)
        video_manager.start()
        return {"message": "Video source changed", "source": source, "status": video_manager.get_status()}
    except Exception as e:
        logger.exception("Failed to change video source")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/video/source")
async def get_video_source():
    """Get current video source"""
    return {"source": str(video_manager.source), "source_type": video_manager.source_type}

@app.get("/video/status")
async def get_video_status():
    """Get video stream health status"""
    return video_manager.get_status()

@app.post("/video/reconnect")
async def reconnect_video():
    """Manually trigger video reconnection"""
    video_manager._attempt_reconnect()
    return {"message": "Reconnection attempted", "status": video_manager.get_status()}


# ===== FLEET MANAGEMENT ENDPOINTS =====

@app.get("/fleet/status")
async def get_fleet_status():
    """Get status of all drones in the fleet"""
    global _global_swarm_manager
    try:
        if not _global_swarm_manager:
            return {"drones": [], "total": 0}
        fleet_status = _global_swarm_manager.get_fleet_status()
        return {"drones": fleet_status, "total": len(fleet_status), "timestamp": time.time()}
    except Exception as e:
        logger.exception("Failed to get fleet status")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fleet/drone/{sys_id}")
async def get_drone_status(sys_id: int):
    """Get status of a specific drone"""
    global _global_swarm_manager
    try:
        if not _global_swarm_manager:
            raise HTTPException(status_code=404, detail="Fleet manager not initialized")
        drone = _global_swarm_manager.get_drone(sys_id)
        if not drone:
            raise HTTPException(status_code=404, detail=f"Drone {sys_id} not found")
        return {"sys_id": sys_id, "status": drone.status.__dict__, "connected": drone.master is not None}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get drone {sys_id} status")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fleet/telemetry/{sys_id}")
async def get_drone_telemetry(sys_id: int):
    """Get telemetry for a specific drone"""
    global _global_swarm_manager
    try:
        if not _global_swarm_manager:
            raise HTTPException(status_code=404, detail="Fleet manager not initialized")
        drone = _global_swarm_manager.get_drone(sys_id)
        if not drone:
            raise HTTPException(status_code=404, detail=f"Drone {sys_id} not found")
        telemetry = {
            "sys_id": sys_id,
            "gps": {"latitude": drone.status.latitude, "longitude": drone.status.longitude, 
                   "altitude": drone.status.altitude, "satellites": drone.status.satellites_visible},
            "battery": {"voltage": drone.status.battery_voltage, "current": drone.status.battery_current,
                       "remaining": drone.status.battery_remaining},
            "status": {"mode": drone.status.mode, "armed": drone.status.armed}
        }
        return telemetry
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get drone {sys_id} telemetry")
        raise HTTPException(status_code=500, detail=str(e))

# ===== EVENT LOGGING ENDPOINTS =====

@app.get("/events/{session_id}")
async def get_session_events(session_id: str, event_type: Optional[str] = None, drone_id: Optional[int] = None):
    """Get all events for a session"""
    try:
        events = event_logger.get_session_events(session_id, event_type, drone_id)
        return {"session_id": session_id, "events": events, "total": len(events)}
    except Exception as e:
        logger.exception("Failed to get session events")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/export/{session_id}")
async def export_session_events(session_id: str, format: str = "json"):
    """Export session events as JSON or CSV"""
    from fastapi.responses import Response
    try:
        if format not in ["json", "csv"]:
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
        data = event_logger.export_events(session_id, format)
        if data is None:
            raise HTTPException(status_code=500, detail="Failed to export events")
        media_type = "application/json" if format == "json" else "text/csv"
        filename = f"events_{session_id}.{format}"
        return Response(content=data, media_type=media_type, 
                       headers={"Content-Disposition": f"attachment; filename={filename}"})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to export events")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/stats/{session_id}")
async def get_event_statistics(session_id: str):
    """Get event statistics for a session"""
    try:
        stats = event_logger.get_statistics(session_id)
        return {"session_id": session_id, "statistics": stats}
    except Exception as e:
        logger.exception("Failed to get event statistics")
        raise HTTPException(status_code=500, detail=str(e))
