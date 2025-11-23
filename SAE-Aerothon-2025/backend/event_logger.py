"""
Event Logger - Mission Event Tracking System

Logs all mission events to database for post-mission analysis and replay.
Tracks disaster detections, navigation events, payload drops, and more.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from database import MissionEvent, SessionLocal

logger = logging.getLogger(__name__)

class EventLogger:
    """Logs mission events to database"""
    
    def __init__(self):
        self.current_session_id = None
        self.event_count = 0
    
    def set_session(self, session_id: str):
        """Set the current session ID for logging"""
        self.current_session_id = session_id
        logger.info(f"EventLogger session set to: {session_id}")
    
    def log_event(
        self,
        event_type: str,
        drone_id: int = 1,
        event_data: Optional[Dict[str, Any]] = None,
        location: Optional[Dict[str, float]] = None,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Log a mission event to database
        
        Args:
            event_type: Type of event ('disaster_detected', 'navigation', 'payload_drop', etc.)
            drone_id: Drone system ID
            event_data: Additional event-specific data
            location: Optional location dict with 'latitude', 'longitude', 'altitude'
            session_id: Optional session ID (uses current if not provided)
        
        Returns:
            True if logged successfully
        """
        try:
            db = SessionLocal()
            
            # Use provided session_id or current
            sid = session_id or self.current_session_id
            
            # Extract location if provided
            lat = location.get('latitude') if location else None
            lon = location.get('longitude') if location else None
            alt = location.get('altitude') if location else None
            
            # Create event
            event = MissionEvent(
                session_id=sid,
                drone_id=drone_id,
                event_type=event_type,
                event_data=event_data or {},
                timestamp=datetime.now(),
                latitude=lat,
                longitude=lon,
                altitude=alt
            )
            
            db.add(event)
            db.commit()
            db.close()
            
            self.event_count += 1
            logger.info(f"Event logged: {event_type} (drone {drone_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            return False
    
    def log_disaster_detection(
        self,
        drone_id: int,
        disaster_type: str,
        confidence: float,
        safe_spots: List[Dict],
        location: Optional[Dict] = None
    ):
        """Log disaster detection event"""
        event_data = {
            "disaster_type": disaster_type,
            "confidence": confidence,
            "safe_landing_spots": safe_spots,
            "timestamp": datetime.now().isoformat()
        }
        return self.log_event(
            event_type="disaster_detected",
            drone_id=drone_id,
            event_data=event_data,
            location=location
        )
    
    def log_navigation_event(
        self,
        drone_id: int,
        action: str,
        details: Dict,
        location: Optional[Dict] = None
    ):
        """Log navigation event (mode change, waypoint reached, etc.)"""
        event_data = {
            "action": action,
            **details
        }
        return self.log_event(
            event_type="navigation",
            drone_id=drone_id,
            event_data=event_data,
            location=location
        )
    
    def log_payload_drop(
        self,
        drone_id: int,
        payload_type: str,
        success: bool,
        location: Optional[Dict] = None
    ):
        """Log payload drop event"""
        event_data = {
            "payload_type": payload_type,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        return self.log_event(
            event_type="payload_drop",
            drone_id=drone_id,
            event_data=event_data,
            location=location
        )
    
    def get_session_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        drone_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get all events for a session
        
        Args:
            session_id: Session ID to query
            event_type: Optional filter by event type
            drone_id: Optional filter by drone ID
        
        Returns:
            List of event dictionaries
        """
        try:
            db = SessionLocal()
            
            query = db.query(MissionEvent).filter(MissionEvent.session_id == session_id)
            
            if event_type:
                query = query.filter(MissionEvent.event_type == event_type)
            
            if drone_id is not None:
                query = query.filter(MissionEvent.drone_id == drone_id)
            
            events = query.order_by(MissionEvent.timestamp).all()
            
            result = []
            for event in events:
                result.append({
                    "id": event.id,
                    "session_id": event.session_id,
                    "drone_id": event.drone_id,
                    "event_type": event.event_type,
                    "event_data": event.event_data,
                    "timestamp": event.timestamp.isoformat(),
                    "latitude": event.latitude,
                    "longitude": event.longitude,
                    "altitude": event.altitude
                })
            
            db.close()
            return result
            
        except Exception as e:
            logger.error(f"Failed to get session events: {e}")
            return []
    
    def export_events(
        self,
        session_id: str,
        format: str = 'json'
    ) -> Optional[str]:
        """
        Export events to JSON or CSV format
        
        Args:
            session_id: Session ID to export
            format: 'json' or 'csv'
        
        Returns:
            Formatted string or None on error
        """
        events = self.get_session_events(session_id)
        
        if format == 'json':
            import json
            return json.dumps(events, indent=2)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            if events:
                fieldnames = ['id', 'session_id', 'drone_id', 'event_type', 'timestamp', 
                             'latitude', 'longitude', 'altitude']
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(events)
            
            return output.getvalue()
        
        else:
            logger.error(f"Unsupported export format: {format}")
            return None
    
    def get_statistics(self, session_id: str) -> Dict:
        """Get event statistics for a session"""
        events = self.get_session_events(session_id)
        
        stats = {
            "total_events": len(events),
            "by_type": {},
            "by_drone": {},
            "disaster_detections": 0,
            "payload_drops": 0
        }
        
        for event in events:
            # Count by type
            event_type = event['event_type']
            stats['by_type'][event_type] = stats['by_type'].get(event_type, 0) + 1
            
            # Count by drone
            drone_id = event['drone_id']
            stats['by_drone'][drone_id] = stats['by_drone'].get(drone_id, 0) + 1
            
            # Special counters
            if event_type == 'disaster_detected':
                stats['disaster_detections'] += 1
            elif event_type == 'payload_drop':
                stats['payload_drops'] += 1
        
        return stats

# Global event logger instance
event_logger = EventLogger()
