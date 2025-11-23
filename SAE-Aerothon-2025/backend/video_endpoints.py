# ===== VIDEO SOURCE MANAGEMENT ENDPOINTS =====

@app.post("/video/source")
async def set_video_source(source: str = Body(..., embed=True)):
    """Change video source dynamically"""
    global video_manager
    try:
        logger.info(f"Changing video source to: {source}")
        
        # Stop current video manager
        video_manager.stop()
        
        # Parse source (convert "0" to int 0)
        parsed_source = int(source) if source.isdigit() else source
        
        # Create new video manager
        video_manager = VideoManager(source=parsed_source)
        video_manager.start()
        
        return {
            "message": "Video source changed successfully",
            "source": source,
            "status": video_manager.get_status()
        }
    except Exception as e:
        logger.exception("Failed to change video source")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/video/source")
async def get_video_source():
    """Get current video source"""
    try:
        return {
            "source": str(video_manager.source),
            "source_type": video_manager.source_type
        }
    except Exception as e:
        logger.exception("Failed to get video source")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/video/status")
async def get_video_status():
    """Get video stream health status"""
    try:
        return video_manager.get_status()
    except Exception as e:
        logger.exception("Failed to get video status")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/video/reconnect")
async def reconnect_video():
    """Manually trigger video reconnection"""
    try:
        logger.info("Manual video reconnection triggered")
        video_manager._attempt_reconnect()
        return {
            "message": "Reconnection attempted",
            "status": video_manager.get_status()
        }
    except Exception as e:
        logger.exception("Failed to reconnect video")
        raise HTTPException(status_code=500, detail=str(e))
