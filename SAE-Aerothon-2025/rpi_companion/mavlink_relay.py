#!/usr/bin/env python3
"""
MAVLink Relay Module

Relays MAVLink telemetry from Pixhawk to GCS and forwards commands from GCS to Pixhawk.
Handles bidirectional MAVLink communication over serial and UDP.
"""

import logging
import time
import socket
from pymavlink import mavutil
from threading import Thread, Lock

logger = logging.getLogger('mavlink_relay')

class MAVLinkRelay:
    """Bidirectional MAVLink relay between Pixhawk and GCS"""
    
    def __init__(self, pixhawk_port, pixhawk_baud, gcs_ip, gcs_telemetry_port, gcs_command_port):
        self.pixhawk_port = pixhawk_port
        self.pixhawk_baud = pixhawk_baud
        self.gcs_ip = gcs_ip
        self.gcs_telemetry_port = gcs_telemetry_port
        self.gcs_command_port = gcs_command_port
        self.running = False
        
        # MAVLink connections
        self.pixhawk = None
        self.gcs_telemetry_sock = None
        self.gcs_command_sock = None
        
        # Statistics
        self.telemetry_sent = 0
        self.commands_received = 0
        self.last_heartbeat = 0
        self.lock = Lock()
        
    def _connect_pixhawk(self):
        """Connect to Pixhawk via serial"""
        try:
            logger.info(f"Connecting to Pixhawk on {self.pixhawk_port} @ {self.pixhawk_baud} baud...")
            self.pixhawk = mavutil.mavlink_connection(
                self.pixhawk_port,
                baud=self.pixhawk_baud,
                source_system=255  # GCS system ID
            )
            
            # Wait for heartbeat
            logger.info("Waiting for Pixhawk heartbeat...")
            self.pixhawk.wait_heartbeat(timeout=10)
            logger.info(f"✓ Pixhawk connected (system {self.pixhawk.target_system}, component {self.pixhawk.target_component})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Pixhawk: {e}")
            return False
    
    def _init_sockets(self):
        """Initialize UDP sockets for GCS communication"""
        try:
            # Telemetry output socket (to GCS)
            self.gcs_telemetry_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.info(f"Telemetry socket initialized for {self.gcs_ip}:{self.gcs_telemetry_port}")
            
            # Command input socket (from GCS)
            self.gcs_command_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.gcs_command_sock.bind(('0.0.0.0', self.gcs_command_port))
            self.gcs_command_sock.settimeout(0.1)  # Non-blocking with timeout
            logger.info(f"Command socket listening on port {self.gcs_command_port}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize sockets: {e}")
            return False
    
    def run(self):
        """Main relay loop"""
        logger.info("MAVLink relay starting...")
        
        # Connect to Pixhawk
        if not self._connect_pixhawk():
            logger.error("Pixhawk connection failed, exiting")
            return
        
        # Initialize sockets
        if not self._init_sockets():
            logger.error("Socket initialization failed, exiting")
            return
        
        self.running = True
        
        # Start command receiver thread
        command_thread = Thread(target=self._command_receiver_loop, daemon=True)
        command_thread.start()
        
        logger.info("MAVLink relay running")
        
        # Main telemetry forwarding loop
        while self.running:
            try:
                # Receive message from Pixhawk
                msg = self.pixhawk.recv_match(blocking=True, timeout=1.0)
                
                if msg is None:
                    continue
                
                # Forward to GCS
                self._forward_to_gcs(msg)
                
                # Track heartbeats
                if msg.get_type() == 'HEARTBEAT':
                    self.last_heartbeat = time.time()
                
            except Exception as e:
                logger.error(f"Telemetry relay error: {e}")
                time.sleep(0.1)
        
        self._cleanup()
    
    def _forward_to_gcs(self, msg):
        """Forward MAVLink message to GCS"""
        try:
            # Pack message
            packed = msg.pack(self.pixhawk.mav)
            
            # Send via UDP
            self.gcs_telemetry_sock.sendto(packed, (self.gcs_ip, self.gcs_telemetry_port))
            
            with self.lock:
                self.telemetry_sent += 1
                
                # Log statistics every 100 messages
                if self.telemetry_sent % 100 == 0:
                    logger.debug(f"Telemetry forwarded: {self.telemetry_sent} messages")
                    
        except Exception as e:
            logger.error(f"Failed to forward telemetry: {e}")
    
    def _command_receiver_loop(self):
        """Receive commands from GCS and forward to Pixhawk"""
        logger.info("Command receiver started")
        
        while self.running:
            try:
                # Receive command from GCS
                data, addr = self.gcs_command_sock.recvfrom(4096)
                
                if not data:
                    continue
                
                # Forward to Pixhawk
                self.pixhawk.write(data)
                
                with self.lock:
                    self.commands_received += 1
                    
                logger.debug(f"Command forwarded from {addr}")
                
            except socket.timeout:
                # Normal timeout, continue
                continue
            except Exception as e:
                if self.running:  # Only log if not shutting down
                    logger.error(f"Command receiver error: {e}")
                time.sleep(0.1)
        
        logger.info("Command receiver stopped")
    
    def get_statistics(self):
        """Get relay statistics"""
        with self.lock:
            return {
                'telemetry_sent': self.telemetry_sent,
                'commands_received': self.commands_received,
                'last_heartbeat': self.last_heartbeat,
                'heartbeat_age': time.time() - self.last_heartbeat if self.last_heartbeat > 0 else None
            }
    
    def stop(self):
        """Stop relay"""
        logger.info("Stopping MAVLink relay...")
        self.running = False
    
    def _cleanup(self):
        """Clean up resources"""
        if self.pixhawk:
            self.pixhawk.close()
        if self.gcs_telemetry_sock:
            self.gcs_telemetry_sock.close()
        if self.gcs_command_sock:
            self.gcs_command_sock.close()
        logger.info("MAVLink relay stopped")

if __name__ == "__main__":
    # Test standalone
    logging.basicConfig(level=logging.INFO)
    relay = MAVLinkRelay(
        pixhawk_port="/dev/ttyACM0",
        pixhawk_baud=57600,
        gcs_ip="192.168.1.100",
        gcs_telemetry_port=14550,
        gcs_command_port=14551
    )
    relay.run()
