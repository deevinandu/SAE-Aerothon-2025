import cv2
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import logging
import threading

logger = logging.getLogger(__name__)

class VideoRecorder:
    def __init__(self, recordings_dir: str = "recordings"):
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(exist_ok=True)
        
        self.is_recording = False
        self.video_writer: Optional[cv2.VideoWriter] = None
        self.session_dir: Optional[Path] = None
        self.ai_analyses: List[Dict] = []
        self.start_time: Optional[datetime] = None
        self.frame_count = 0
        self.lock = threading.Lock()
        
        # Video settings
        self.fps = 30
        self.frame_size = (640, 480)
        self.codec = cv2.VideoWriter_fourcc(*'mp4v')
        
    def start_recording(self, session_id: str) -> Dict:
        """Start a new recording session"""
        with self.lock:
            if self.is_recording:
                return {"error": "Recording already in progress"}
            
            # Create session directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = f"session_{timestamp}_{session_id[:8]}"
            self.session_dir = self.recordings_dir / session_name
            self.session_dir.mkdir(exist_ok=True)
            
            # Initialize video writer
            video_path = self.session_dir / "video.mp4"
            self.video_writer = cv2.VideoWriter(
                str(video_path),
                self.codec,
                self.fps,
                self.frame_size
            )
            
            if not self.video_writer.isOpened():
                logger.error("Failed to open video writer")
                return {"error": "Failed to initialize video writer"}
            
            # Reset state
            self.ai_analyses = []
            self.start_time = datetime.now()
            self.frame_count = 0
            self.is_recording = True
            
            logger.info(f"Recording started: {session_name}")
            return {
                "status": "recording",
                "session_dir": str(self.session_dir),
                "start_time": self.start_time.isoformat()
            }
    
    def add_frame(self, frame):
        """Add a frame to the recording with timestamp overlay"""
        if not self.is_recording or self.video_writer is None:
            return
        
        with self.lock:
            # Create a copy to avoid modifying the original
            frame_copy = frame.copy()
            
            # Add timestamp overlay
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cv2.putText(
                frame_copy,
                timestamp,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),  # Cyan color
                2,
                cv2.LINE_AA
            )
            
            # Write frame
            self.video_writer.write(frame_copy)
            self.frame_count += 1
    
    def add_ai_analysis(self, analysis: Dict):
        """Add AI analysis result to the log"""
        if not self.is_recording:
            return
        
        with self.lock:
            # Add timestamp and frame number
            analysis_entry = {
                "timestamp": datetime.now().isoformat(),
                "frame_number": self.frame_count,
                **analysis
            }
            self.ai_analyses.append(analysis_entry)
    
    def stop_recording(self) -> Dict:
        """Stop recording and save all files"""
        with self.lock:
            if not self.is_recording:
                return {"error": "No recording in progress"}
            
            # Release video writer
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds()
            
            # Save AI analysis log
            ai_log = {
                "session_id": self.session_dir.name if self.session_dir else "unknown",
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "total_frames": self.frame_count,
                "analyses": self.ai_analyses
            }
            
            ai_log_path = self.session_dir / "ai_analysis.json"
            with open(ai_log_path, 'w') as f:
                json.dump(ai_log, f, indent=2)
            
            # Save metadata
            metadata = {
                "session_id": self.session_dir.name if self.session_dir else "unknown",
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "total_frames": self.frame_count,
                "fps": self.fps,
                "resolution": f"{self.frame_size[0]}x{self.frame_size[1]}",
                "total_analyses": len(self.ai_analyses)
            }
            
            metadata_path = self.session_dir / "metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Recording stopped: {self.session_dir.name}, Duration: {duration:.2f}s, Frames: {self.frame_count}")
            
            result = {
                "status": "stopped",
                "session_dir": str(self.session_dir),
                "duration_seconds": duration,
                "total_frames": self.frame_count,
                "total_analyses": len(self.ai_analyses)
            }
            
            # Reset state
            self.is_recording = False
            self.session_dir = None
            self.ai_analyses = []
            self.start_time = None
            self.frame_count = 0
            
            return result
    
    def get_status(self) -> Dict:
        """Get current recording status"""
        with self.lock:
            if not self.is_recording:
                return {"status": "idle"}
            
            duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
            return {
                "status": "recording",
                "session_dir": str(self.session_dir) if self.session_dir else None,
                "duration_seconds": duration,
                "frame_count": self.frame_count,
                "analyses_count": len(self.ai_analyses)
            }
    
    def list_recordings(self) -> List[Dict]:
        """List all saved recordings"""
        recordings = []
        for session_dir in sorted(self.recordings_dir.iterdir(), reverse=True):
            if session_dir.is_dir():
                metadata_path = session_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    recordings.append({
                        "session_name": session_dir.name,
                        "path": str(session_dir),
                        **metadata
                    })
        return recordings
