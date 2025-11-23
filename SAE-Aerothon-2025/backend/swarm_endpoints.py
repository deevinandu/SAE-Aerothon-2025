# ===== FLEET MANAGEMENT ENDPOINTS =====

@app.get("/fleet/status")
async def get_swarm_status():
    """Get status of all drones in the fleet"""
    global _global_swarm_manager
    try:
        if not _global_swarm_manager:
            return {"drones": [], "total": 0}
        
        fleet_status = _global_swarm_manager.get_swarm_status()
        return {
            "drones": fleet_status,
            "total": len(fleet_status),
            "timestamp": time.time()
        }
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
        
        return {
            "sys_id": sys_id,
            "status": drone.status.__dict__,
            "connected": drone.master is not None,
            "timestamp": time.time()
        }
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
        
        # Get latest telemetry from drone status
        telemetry = {
            "sys_id": sys_id,
            "gps": {
                "latitude": drone.status.latitude,
                "longitude": drone.status.longitude,
                "altitude": drone.status.altitude,
                "satellites": drone.status.satellites_visible
            },
            "battery": {
                "voltage": drone.status.battery_voltage,
                "current": drone.status.battery_current,
                "remaining": drone.status.battery_remaining
            },
            "status": {
                "mode": drone.status.mode,
                "armed": drone.status.armed
            },
            "timestamp": time.time()
        }
        
        return telemetry
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get drone {sys_id} telemetry")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fleet/drone/{sys_id}/command")
async def send_drone_command(sys_id: int, command: str = Body(..., embed=True), params: dict = Body(default={})):
    """Send command to a specific drone"""
    global _global_swarm_manager
    try:
        if not _global_swarm_manager:
            raise HTTPException(status_code=404, detail="Fleet manager not initialized")
        
        drone = _global_swarm_manager.get_drone(sys_id)
        if not drone:
            raise HTTPException(status_code=404, detail=f"Drone {sys_id} not found")
        
        # Log command event
        event_logger.log_navigation_event(
            drone_id=sys_id,
            action=f"command_{command}",
            details=params
        )
        
        # Execute command based on type
        if command == "arm":
            drone.arm()
        elif command == "disarm":
            drone.disarm()
        elif command == "set_mode":
            mode = params.get("mode")
            if not mode:
                raise HTTPException(status_code=400, detail="Mode parameter required")
            drone.set_mode(mode)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown command: {command}")
        
        return {
            "message": f"Command '{command}' sent to drone {sys_id}",
            "sys_id": sys_id,
            "command": command,
            "params": params
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send command to drone {sys_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== EVENT LOGGING ENDPOINTS =====

@app.get("/events/{session_id}")
async def get_session_events(
    session_id: str,
    event_type: Optional[str] = None,
    drone_id: Optional[int] = None
):
    """Get all events for a session"""
    try:
        events = event_logger.get_session_events(session_id, event_type, drone_id)
        return {
            "session_id": session_id,
            "events": events,
            "total": len(events)
        }
    except Exception as e:
        logger.exception("Failed to get session events")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/export/{session_id}")
async def export_session_events(session_id: str, format: str = "json"):
    """Export session events as JSON or CSV"""
    try:
        if format not in ["json", "csv"]:
            raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
        
        data = event_logger.export_events(session_id, format)
        if data is None:
            raise HTTPException(status_code=500, detail="Failed to export events")
        
        media_type = "application/json" if format == "json" else "text/csv"
        filename = f"events_{session_id}.{format}"
        
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
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
        return {
            "session_id": session_id,
            "statistics": stats
        }
    except Exception as e:
        logger.exception("Failed to get event statistics")
        raise HTTPException(status_code=500, detail=str(e))
