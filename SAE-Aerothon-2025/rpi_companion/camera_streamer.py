#!/usr/bin/env python3
"""
Camera Streamer Module

Captures video from RPi camera or USB webcam and streams to GCS via UDP.
Optimized for low latency with configurable resolution and quality.
"""

import cv2
import socket
import logging
import time
import numpy as np
from threading import Lock

logger = logging.getLogger('camera_streamer')

class CameraStreamer:
    """Streams camera feed to GCS via UDP"""
    
    def __init__(self, gcs_ip, gcs_port, camera_device=0, width=640, height=480, fps=30, quality=80):
        self.gcs_ip = gcs_ip
        self.gcs_port = gcs_port
        self.camera_device = camera_device
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self.running = False
        
        # Initialize camera
        self.cap = None
        self.sock = None
        self.lock = Lock()
        
        # Statistics
        self.frames_sent = 0
        self.bytes_sent = 0
        self.last_stats_time = time.time()
        
    def _init_camera(self):
        """Initialize camera with optimized settings"""
        try:
            self.cap = cv2.VideoCapture(self.camera_device)
            
            if not self.cap.isOpened():
                raise Exception(f"Failed to open camera device {self.camera_device}")
            
            # Set camera properties for low latency
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffering
            
            # Verify settings
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self.cap.get(cv2.CAP_PROP_FPS))
            
            logger.info(f"Camera initialized: {actual_width}x{actual_height} @ {actual_fps}fps")
            return True
            
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return False
    
    def _init_socket(self):
        """Initialize UDP socket for streaming"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Set socket buffer size for better performance
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            logger.info(f"UDP socket initialized for {self.gcs_ip}:{self.gcs_port}")
            return True
        except Exception as e:
            logger.error(f"Socket initialization failed: {e}")
            return False
    
    def run(self):
        """Main streaming loop"""
        logger.info("Camera streamer starting...")
        
        # Initialize camera and socket
        if not self._init_camera():
            logger.error("Camera initialization failed, exiting")
            return
        
        if not self._init_socket():
            logger.error("Socket initialization failed, exiting")
            return
        
        self.running = True
        frame_interval = 1.0 / self.fps
        
        logger.info(f"Streaming to {self.gcs_ip}:{self.gcs_port}")
        
        while self.running:
            try:
                start_time = time.time()
                
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("Failed to capture frame")
                    time.sleep(0.1)
                    continue
                
                # Encode frame as JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                ret, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                if not ret:
                    logger.warning("Failed to encode frame")
                    continue
                
                # Send via UDP (split into chunks if needed)
                data = buffer.tobytes()
                chunk_size = 60000  # Max UDP packet size (safe value)
                
                if len(data) <= chunk_size:
                    # Send as single packet
                    self.sock.sendto(data, (self.gcs_ip, self.gcs_port))
                else:
                    # Split into chunks (for high quality/resolution)
                    for i in range(0, len(data), chunk_size):
                        chunk = data[i:i+chunk_size]
                        self.sock.sendto(chunk, (self.gcs_ip, self.gcs_port))
                
                # Update statistics
                self.frames_sent += 1
                self.bytes_sent += len(data)
                
                # Log statistics every 10 seconds
                if time.time() - self.last_stats_time > 10:
                    self._log_statistics()
                
                # Maintain frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                time.sleep(0.1)
        
        self._cleanup()
    
    def _log_statistics(self):
        """Log streaming statistics"""
        elapsed = time.time() - self.last_stats_time
        fps = self.frames_sent / elapsed
        mbps = (self.bytes_sent * 8) / (elapsed * 1_000_000)
        
        logger.info(f"Stream stats: {fps:.1f} fps, {mbps:.2f} Mbps, {self.frames_sent} frames")
        
        # Reset counters
        self.frames_sent = 0
        self.bytes_sent = 0
        self.last_stats_time = time.time()
    
    def stop(self):
        """Stop streaming"""
        logger.info("Stopping camera streamer...")
        self.running = False
    
    def _cleanup(self):
        """Clean up resources"""
        if self.cap:
            self.cap.release()
        if self.sock:
            self.sock.close()
        logger.info("Camera streamer stopped")

if __name__ == "__main__":
    # Test standalone
    logging.basicConfig(level=logging.INFO)
    streamer = CameraStreamer(
        gcs_ip="192.168.1.100",
        gcs_port=5600,
        camera_device=0,
        width=640,
        height=480,
        fps=30,
        quality=80
    )
    streamer.run()
