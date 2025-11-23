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
