import cv2
import threading
import time
import logging
import socket
import numpy as np
from typing import Optional, Generator, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class VideoManager:
    """
    Manages video capture from multiple sources with automatic error recovery.
    
    Supported sources:
    - Webcam: source=0 (or any integer)
    - UDP: source="udp://0.0.0.0:5600"
    - RTSP: source="rtsp://..."
    - File: source="/path/to/video.mp4"
    """
    
    def __init__(self, source: Union[int, str] = 0, max_retries: int = 5, retry_delay: int = 2):
        self.source = source
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_count = 0
        
        # Parse source type
        self.source_type = self._detect_source_type(source)
        
        # Connection state
        self.is_healthy = False
        self.last_frame_time = 0
        self.connection_attempts = 0
        self.last_error = None
        
        # Video capture
        self.cap = None
        self.udp_socket = None
        self.lock = threading.Lock()
        self.current_frame = None
        self.running = False
        self.thread = None
        
        # Statistics
        self.frames_received = 0
        self.frames_dropped = 0
        
        # Initialize connection
        self._initialize_source()
    
    def _detect_source_type(self, source: Union[int, str]) -> str:
        """Detect the type of video source"""
        if isinstance(source, int):
            return "webcam"
        
        source_str = str(source).lower()
        
        if source_str.startswith("udp://"):
            return "udp"
        elif source_str.startswith("rtsp://"):
            return "rtsp"
        elif source_str.startswith("http://") or source_str.startswith("https://"):
            return "http"
        elif source_str.endswith(('.mp4', '.avi', '.mkv', '.mov')):
            return "file"
        else:
            # Try as file path
            return "file"
    
    def _initialize_source(self) -> bool:
        """Initialize video source based on type"""
        try:
            if self.source_type == "webcam":
                return self._init_webcam()
            elif self.source_type == "udp":
                return self._init_udp()
            elif self.source_type in ["rtsp", "http", "file"]:
                return self._init_opencv_source()
            else:
                logger.error(f"Unsupported source type: {self.source_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize source: {e}")
            self.last_error = str(e)
            return False
    
    def _init_webcam(self) -> bool:
        """Initialize webcam source"""
        try:
            self.cap = cv2.VideoCapture(self.source)
            
            if not self.cap.isOpened():
                raise Exception(f"Failed to open webcam {self.source}")
            
            # Optimize for low latency
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.is_healthy = True
            logger.info(f"Webcam initialized: {self.source}")
            return True
            
        except Exception as e:
            logger.error(f"Webcam initialization failed: {e}")
            self.last_error = str(e)
            return False
    
    def _init_udp(self) -> bool:
        """Initialize UDP video receiver"""
        try:
            # Parse UDP URL
            parsed = urlparse(self.source)
            host = parsed.hostname or "0.0.0.0"
            port = parsed.port or 5600
            
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self.udp_socket.bind((host, port))
            self.udp_socket.settimeout(1.0)  # 1 second timeout
            
            self.is_healthy = True
            logger.info(f"UDP receiver initialized: {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"UDP initialization failed: {e}")
            self.last_error = str(e)
            return False
    
    def _init_opencv_source(self) -> bool:
        """Initialize RTSP/HTTP/File source using OpenCV"""
        try:
            self.cap = cv2.VideoCapture(str(self.source))
            
            if not self.cap.isOpened():
                raise Exception(f"Failed to open source: {self.source}")
            
            # Set buffer size for network streams
            if self.source_type in ["rtsp", "http"]:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.is_healthy = True
            logger.info(f"{self.source_type.upper()} source initialized: {self.source}")
            return True
            
        except Exception as e:
            logger.error(f"{self.source_type.upper()} initialization failed: {e}")
            self.last_error = str(e)
            return False
    
    def start(self):
        """Start video capture thread"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        logger.info(f"VideoManager started ({self.source_type}): {self.source}")
    
    def stop(self):
        """Stop video capture"""
        logger.info("Stopping VideoManager...")
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self._cleanup()
    
    def _update_loop(self):
        """Main video capture loop with error recovery"""
        while self.running:
            try:
                if self.source_type == "udp":
                    self._update_udp()
                else:
                    self._update_opencv()
                
                # Check health
                self._check_health()
                
            except Exception as e:
                logger.error(f"Update loop error: {e}")
                self.is_healthy = False
                self._attempt_reconnect()
                time.sleep(0.1)
    
    def _update_opencv(self):
        """Update frame from OpenCV source"""
        if not self.cap or not self.cap.isOpened():
            self._attempt_reconnect()
            time.sleep(1)
            return
        
        ret, frame = self.cap.read()
        
        if ret:
            with self.lock:
                self.current_frame = frame
                self.last_frame_time = time.time()
                self.frames_received += 1
            self.retry_count = 0  # Reset on success
        else:
            logger.warning(f"Failed to read frame from {self.source_type} source")
            self.frames_dropped += 1
            self._attempt_reconnect()
        
        # Small sleep to prevent CPU overload
        time.sleep(0.01)
    
    def _update_udp(self):
        """Update frame from UDP source"""
        if not self.udp_socket:
            self._attempt_reconnect()
            time.sleep(1)
            return
        
        try:
            # Receive UDP packet
            data, addr = self.udp_socket.recvfrom(65536)
            
            if not data:
                return
            
            # Decode JPEG frame
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                with self.lock:
                    self.current_frame = frame
                    self.last_frame_time = time.time()
                    self.frames_received += 1
                self.retry_count = 0  # Reset on success
            else:
                self.frames_dropped += 1
                
        except socket.timeout:
            # Normal timeout, continue
            pass
        except Exception as e:
            logger.error(f"UDP receive error: {e}")
            self.frames_dropped += 1
            self._attempt_reconnect()
    
    def _check_health(self):
        """Check if video source is healthy"""
        if self.last_frame_time == 0:
            return  # No frames yet
        
        # Check for stale frames (no new frames for 5 seconds)
        time_since_last_frame = time.time() - self.last_frame_time
        
        if time_since_last_frame > 5:
            logger.warning(f"No frames received for {time_since_last_frame:.1f}s")
            self.is_healthy = False
            self._attempt_reconnect()
        else:
            self.is_healthy = True
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to video source"""
        if self.retry_count >= self.max_retries:
            logger.error(f"Max reconnection attempts ({self.max_retries}) reached")
            return
        
        self.retry_count += 1
        delay = self.retry_delay * (2 ** (self.retry_count - 1))  # Exponential backoff
        
        logger.info(f"Attempting reconnection {self.retry_count}/{self.max_retries} in {delay}s...")
        time.sleep(delay)
        
        # Cleanup old connection
        self._cleanup()
        
        # Try to reinitialize
        if self._initialize_source():
            logger.info("Reconnection successful!")
            self.retry_count = 0
            self.is_healthy = True
        else:
            logger.error(f"Reconnection attempt {self.retry_count} failed")
    
    def _cleanup(self):
        """Clean up resources"""
        if self.cap:
            self.cap.release()
            self.cap = None
        
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
    
    def get_frame(self) -> Optional[bytes]:
        """Get the current frame as JPEG bytes"""
        frame_ref = None
        with self.lock:
            if self.current_frame is not None:
                frame_ref = self.current_frame
        
        if frame_ref is None:
            return None
        
        # Encode as JPEG
        ret, buffer = cv2.imencode('.jpg', frame_ref, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ret:
            return None
        return buffer.tobytes()
    
    def get_latest_frame_cv2(self):
        """Get the raw OpenCV frame (for AI analysis)"""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None
    
    def generate_mjpeg(self) -> Generator[bytes, None, None]:
        """Generate MJPEG stream for HTTP response"""
        while True:
            frame_bytes = self.get_frame()
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                # If no frame, yield a small placeholder
                pass
            # Target ~30 FPS
            time.sleep(0.033)
    
    def get_status(self) -> dict:
        """Get video source status"""
        return {
            "source": str(self.source),
            "source_type": self.source_type,
            "is_healthy": self.is_healthy,
            "is_running": self.running,
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "retry_count": self.retry_count,
            "last_frame_age": time.time() - self.last_frame_time if self.last_frame_time > 0 else None,
            "last_error": self.last_error
        }
