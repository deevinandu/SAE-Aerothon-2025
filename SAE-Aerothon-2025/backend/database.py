import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import json

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Database setup
DATABASE_URL = "sqlite:///./gcs.db"
Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.now)
    frame_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    
    # Relationships
    frames = relationship("SessionFrame", back_populates="session", cascade="all, delete-orphan")
    telemetry = relationship("TelemetryLog", back_populates="session", cascade="all, delete-orphan")

class SessionFrame(Base):
    __tablename__ = "session_frames"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    frame_number = Column(Integer)
    timestamp = Column(DateTime, default=datetime.now)
    
    # Analysis results
    detected_objects = Column(JSON)  # Stored as JSON list of objects
    raw_labels = Column(JSON)        # Stored as JSON list of strings
    
    session = relationship("Session", back_populates="frames")

class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    sys_id = Column(Integer, default=1)
    timestamp = Column(DateTime, default=datetime.now)
    
    # GPS
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    gps_speed = Column(Float, nullable=True)
    gps_heading = Column(Float, nullable=True)
    satellites = Column(Integer, nullable=True)
    
    # Attitude
    roll = Column(Float, nullable=True)
    pitch = Column(Float, nullable=True)
    yaw = Column(Float, nullable=True)
    
    # Battery
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    remaining = Column(Float, nullable=True)
    
    # VFR HUD
    airspeed = Column(Float, nullable=True)
    groundspeed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    throttle = Column(Float, nullable=True)
    climb = Column(Float, nullable=True)
    
    # Status
    mode = Column(String, nullable=True)
    armed = Column(Boolean, nullable=True)
    
    session = relationship("Session", back_populates="telemetry")

class Mission(Base):
    __tablename__ = "missions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    waypoints = Column(JSON)  # Stored as JSON list of waypoints

class MissionEvent(Base):
    __tablename__ = "mission_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=True)
    drone_id = Column(Integer, default=1)
    event_type = Column(String)  # 'disaster_detected', 'navigation', 'payload_drop', etc.
    event_data = Column(JSON)  # Additional event-specific data
    timestamp = Column(DateTime, default=datetime.now)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)

class FlightLog(Base):
    __tablename__ = "flight_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String)
    drone_id = Column(Integer, default=1)
    log_file_path = Column(String)  # Path to .tlog file
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    total_flight_time = Column(Float, nullable=True)  # seconds
    max_altitude = Column(Float, nullable=True)
    total_distance = Column(Float, nullable=True)  # meters
    max_speed = Column(Float, nullable=True)

class RecordingMetadata(Base):
    __tablename__ = "recording_metadata"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String)
    recording_path = Column(String)  # Path to video file
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # seconds
    total_frames = Column(Integer, default=0)
    total_ai_analyses = Column(Integer, default=0)
    drone_id = Column(Integer, nullable=True)
    
# Engine and Session factory
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Helper Functions ---

def create_session(db, session_id: str) -> Session:
    """Create a new session if it doesn't exist"""
    db_session = db.query(Session).filter(Session.id == session_id).first()
    if not db_session:
        db_session = Session(id=session_id, created_at=datetime.now(), frame_count=0)
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
    return db_session

def update_session_frame_count(db, session_id: str, count: int):
    """Update frame count for a session"""
    db_session = db.query(Session).filter(Session.id == session_id).first()
    if db_session:
        db_session.frame_count = count
        db.commit()

def log_frame_analysis(db, session_id: str, frame_number: int, objects: List[Dict], labels: List[str]):
    """Log frame analysis results"""
    # Ensure session exists
    create_session(db, session_id)
    
    frame = SessionFrame(
        session_id=session_id,
        frame_number=frame_number,
        detected_objects=objects,
        raw_labels=labels,
        timestamp=datetime.now()
    )
    db.add(frame)
    db.commit()

def log_telemetry(db, data: Dict[str, Any], session_id: Optional[str] = None, sys_id: int = 1):
    """Log telemetry data snapshot"""
    if session_id:
        # Ensure session exists if provided
        create_session(db, session_id)
    
    # Extract flattened data
    gps = data.get("gps", {})
    att = data.get("attitude", {})
    batt = data.get("battery", {})
    vfr = data.get("vfr_hud", {})
    status = data.get("status", {})
    
    # Helper to safe cast
    def _f(val): return float(val) if val is not None and val != "--" else None
    def _i(val): return int(val) if val is not None and val != "--" else None
    def _b(val): return bool(val) if val is not None and val != "--" else None
    def _s(val): return str(val) if val is not None and val != "--" else None

    log = TelemetryLog(
        session_id=session_id,
        sys_id=sys_id,
        timestamp=datetime.now(),
        
        latitude=_f(gps.get("latitude")),
        longitude=_f(gps.get("longitude")),
        altitude=_f(gps.get("altitude")),
        gps_speed=_f(gps.get("speed")),
        gps_heading=_f(gps.get("heading")),
        satellites=_i(gps.get("satellites")),
        
        roll=_f(att.get("roll")),
        pitch=_f(att.get("pitch")),
        yaw=_f(att.get("yaw")),
        
        voltage=_f(batt.get("voltage")),
        current=_f(batt.get("current")),
        remaining=_f(batt.get("remaining")),
        
        airspeed=_f(vfr.get("airspeed")),
        groundspeed=_f(vfr.get("groundspeed")),
        heading=_f(vfr.get("heading")),
        throttle=_f(vfr.get("throttle")),
        climb=_f(vfr.get("climb")),
        
        mode=_s(status.get("mode")),
        armed=_b(status.get("armed"))
    )
    
    db.add(log)
    db.commit()

def get_session_history(db, session_id: str) -> List[Dict]:
    """Retrieve object history for a session (for context)"""
    # This is a simplified retrieval. For full context, we might need more complex queries.
    # For now, we just return the last few frames' objects to rebuild context if needed,
    # but the current 'contextual' logic relies on in-memory 'objects_seen'.
    # We can persist 'objects_seen' in the Session table if we want full persistence across restarts.
    # For this iteration, we'll stick to logging.
    return []
