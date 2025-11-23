import database
from datetime import datetime

def test_db():
    print("Initializing DB...")
    database.init_db()
    
    db = database.SessionLocal()
    try:
        session_id = "test_session_1"
        print(f"Creating session {session_id}...")
        database.create_session(db, session_id)
        
        print("Logging telemetry...")
        data = {
            "gps": {"latitude": 12.34, "longitude": 56.78, "altitude": 100},
            "attitude": {"roll": 0.1, "pitch": 0.2, "yaw": 0.3},
            "battery": {"voltage": 12.5, "remaining": 80},
            "vfr_hud": {"airspeed": 10, "groundspeed": 12},
            "status": {"mode": "GUIDED", "armed": True}
        }
        database.log_telemetry(db, data, session_id)
        
        print("Verifying data...")
        session = db.query(database.Session).filter(database.Session.id == session_id).first()
        if session:
            print(f"Session found: {session.id}")
            print(f"Telemetry count: {len(session.telemetry)}")
            if len(session.telemetry) > 0:
                print("Telemetry verification SUCCESS")
            else:
                print("Telemetry verification FAILED")
        else:
            print("Session verification FAILED")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_db()
