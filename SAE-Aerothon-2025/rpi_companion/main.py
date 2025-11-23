#!/usr/bin/env python3
"""
Raspberry Pi Companion Computer - Main Entry Point

This script orchestrates the companion computer software running on the drone's RPi.
It manages camera streaming, MAVLink relay, and system monitoring.

Author: SAE Aerothon GCS Team
"""

import sys
import signal
import logging
import threading
import time
import yaml
from pathlib import Path

# Import companion modules
from camera_streamer import CameraStreamer
from mavlink_relay import MAVLinkRelay
from system_monitor import SystemMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/log/companion.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('companion_main')

class CompanionComputer:
    """Main companion computer orchestrator"""
    
    def __init__(self, config_path='config.yaml'):
        self.config = self._load_config(config_path)
        self.running = False
        
        # Initialize components
        self.camera_streamer = None
        self.mavlink_relay = None
        self.system_monitor = None
        
        # Threads
        self.threads = []
        
    def _load_config(self, config_path):
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)
    
    def start(self):
        """Start all companion computer services"""
        logger.info("=" * 60)
        logger.info("Starting Raspberry Pi Companion Computer")
        logger.info("=" * 60)
        
        self.running = True
        
        try:
            # Start camera streamer
            logger.info("Initializing camera streamer...")
            self.camera_streamer = CameraStreamer(
                gcs_ip=self.config['gcs']['ip'],
                gcs_port=self.config['gcs']['video_port'],
                camera_device=self.config['camera']['device'],
                width=self.config['camera']['width'],
                height=self.config['camera']['height'],
                fps=self.config['camera']['fps'],
                quality=self.config['camera']['quality']
            )
            camera_thread = threading.Thread(target=self.camera_streamer.run, daemon=True)
            camera_thread.start()
            self.threads.append(camera_thread)
            logger.info("✓ Camera streamer started")
            
            # Start MAVLink relay
            logger.info("Initializing MAVLink relay...")
            self.mavlink_relay = MAVLinkRelay(
                pixhawk_port=self.config['pixhawk']['serial_port'],
                pixhawk_baud=self.config['pixhawk']['baud_rate'],
                gcs_ip=self.config['gcs']['ip'],
                gcs_telemetry_port=self.config['gcs']['telemetry_port'],
                gcs_command_port=self.config['gcs']['command_port']
            )
            mavlink_thread = threading.Thread(target=self.mavlink_relay.run, daemon=True)
            mavlink_thread.start()
            self.threads.append(mavlink_thread)
            logger.info("✓ MAVLink relay started")
            
            # Start system monitor
            logger.info("Initializing system monitor...")
            self.system_monitor = SystemMonitor(log_interval=30)
            monitor_thread = threading.Thread(target=self.system_monitor.run, daemon=True)
            monitor_thread.start()
            self.threads.append(monitor_thread)
            logger.info("✓ System monitor started")
            
            logger.info("=" * 60)
            logger.info("Companion Computer is RUNNING")
            logger.info(f"  GCS IP: {self.config['gcs']['ip']}")
            logger.info(f"  Video Port: {self.config['gcs']['video_port']}")
            logger.info(f"  Telemetry Port: {self.config['gcs']['telemetry_port']}")
            logger.info("=" * 60)
            
            # Keep main thread alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.stop()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Stop all services gracefully"""
        logger.info("Shutting down companion computer...")
        self.running = False
        
        if self.camera_streamer:
            self.camera_streamer.stop()
        if self.mavlink_relay:
            self.mavlink_relay.stop()
        if self.system_monitor:
            self.system_monitor.stop()
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2)
        
        logger.info("Companion computer stopped")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if companion:
        companion.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start companion computer
    companion = CompanionComputer()
    companion.start()
