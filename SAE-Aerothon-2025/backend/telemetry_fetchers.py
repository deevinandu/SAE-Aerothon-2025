"""
Telemetry Data Fetchers

This module contains placeholder functions for fetching real telemetry data from various sources.
These functions should be implemented based on your specific hardware and data sources.

Current implementation provides random data as fallback.
"""

import random
import math
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import threading
from pymavlink import mavutil

from mavlink_receiver import MavlinkReceiver
from telemetry_config import telemetry_connection_settings


# Configure logging
logger = logging.getLogger(__name__)

# Helper functions to create blank data structures
def blank_telemetry_gps():
    return {"latitude": "--", "longitude": "--", "altitude": "--", "speed": "--", "heading": "--", "fix_type": "--", "satellites": "--", "timestamp": "--"}

def blank_telemetry_attitude():
    return {"roll": "--", "pitch": "--", "yaw": "--", "rollspeed": "--", "pitchspeed": "--", "yawspeed": "--", "timestamp": "--"}

def blank_telemetry_vfr_hud():
    return {"airspeed": "--", "groundspeed": "--", "heading": "--", "throttle": "--", "alt": "--", "climb": "--", "timestamp": "--"}

def blank_telemetry_battery():
    return {"voltage": "--", "current": "--", "remaining": "--", "timestamp": "--"}

def blank_telemetry_system():
    return {"onboard_control_sensors_present": "--", "onboard_control_sensors_enabled": "--", "onboard_control_sensors_health": "--", "load": "--", "voltage_battery": "--", "current_battery": "--", "battery_remaining": "--", "timestamp": "--"}

def blank_telemetry_status():
    return {"armed": "--", "mode": "--"}


# This new global will hold the single MavlinkReceiver instance
_global_mavlink_receiver: Optional["MavlinkReceiver"] = None
_receiver_settings: Dict[str, Any] = {}


def get_global_mavlink_receiver() -> Optional[MavlinkReceiver]:
    """
    Returns the singleton MavlinkReceiver instance.
    It recreates the connection only if connection settings have changed.
    """
    global _global_mavlink_receiver, _receiver_settings

    # Only recreate receiver if settings have changed since the last call
    if telemetry_connection_settings != _receiver_settings:
        logger.info("MAVLink connection settings changed. Re-initializing receiver.")
        
        # Stop the old receiver if it exists
        if _global_mavlink_receiver:
            _global_mavlink_receiver.stop()
        
        _receiver_settings = telemetry_connection_settings.copy()
        
        if not _receiver_settings.get("protocol"):
            logger.warning("No MAVLink protocol configured. Receiver will not connect.")
            _global_mavlink_receiver = None
        else:
            _global_mavlink_receiver = MavlinkReceiver(
                settings=_receiver_settings
            )
    
    return _global_mavlink_receiver

def get_global_mavlink_master() -> Optional[mavutil.mavlink_connection]:
    """
    Returns the active mavlink connection object (master) from the global receiver.
    Returns None if not connected.
    """
    receiver = get_global_mavlink_receiver()
    if receiver and receiver.is_connected():
        return receiver.get_connection()
    return None

# This global will hold the single TelemetryManager instance
_telemetry_manager_instance: Optional["TelemetryManager"] = None


class TelemetryDataFetcher:
    """
    Base class for telemetry data fetching.
    Subclass this to implement real data fetching for your specific hardware.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self.is_connected = False
        
    def connect(self) -> bool:
        """
        Establish connection to telemetry data source.
        Returns True if successful, False otherwise.
        """
        # TODO: Implement actual connection logic
        logger.info(f"TelemetryDataFetcher.connect() called for session {self.session_id}")
        self.is_connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect from telemetry data source."""
        # TODO: Implement actual disconnection logic
        logger.info(f"TelemetryDataFetcher.disconnect() called for session {self.session_id}")
        self.is_connected = False
    
    def is_data_available(self) -> bool:
        """Check if telemetry data is available."""
        # TODO: Implement actual data availability check
        return self.is_connected


class GPSDataFetcher(TelemetryDataFetcher):
    """GPS_RAW_INT message data fetcher"""
    
    def fetch_gps_data(self) -> Dict[str, Any]:
        """
        Fetch GPS_RAW_INT data from MAVLink.
        
        TODO: Implement actual GPS data fetching from MAVLink:
        - Connect to MAVLink stream (UDP, TCP, Serial)
        - Listen for GPS_RAW_INT messages
        - Parse and return structured GPS data
        
        Example implementation:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection('udpin:localhost:14550')
        msg = master.recv_match(type='GPS_RAW_INT', blocking=True)
        if msg:
            return {
                "latitude": msg.lat / 1e7,
                "longitude": msg.lon / 1e7,
                "altitude": msg.alt / 1000,
                "speed": msg.vel / 100,
                "heading": msg.cog / 100,
                "fix_type": msg.fix_type,
                "satellites": msg.satellites_visible,
                "timestamp": datetime.now()
            }
        """
        if not telemetry_connection_settings.get("protocol"):
            return blank_telemetry_gps()
        try:
            rec = get_global_mavlink_receiver()
            data = rec.fetch_gps_data() if rec and rec.is_connected() else None
            if data:
                return data
        except Exception as e:
            pass
        # return last_values["gps"] or blank_telemetry_gps() # This line is removed as per new_code
        return blank_telemetry_gps()


class IMUDataFetcher(TelemetryDataFetcher):
    """ATTITUDE message data fetcher"""
    
    def fetch_imu_data(self) -> Dict[str, Any]:
        """
        Fetch ATTITUDE data from MAVLink.
        
        TODO: Implement actual attitude data fetching from MAVLink:
        - Connect to MAVLink stream (UDP, TCP, Serial)
        - Listen for ATTITUDE messages
        - Parse and return structured attitude data
        
        Example implementation:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection('udpin:localhost:14550')
        msg = master.recv_match(type='ATTITUDE', blocking=True)
        if msg:
            return {
                "roll": msg.roll,
                "pitch": msg.pitch,
                "yaw": msg.yaw,
                "rollspeed": msg.rollspeed,
                "pitchspeed": msg.pitchspeed,
                "yawspeed": msg.yawspeed,
                "timestamp": datetime.now()
            }
        """
        if not telemetry_connection_settings.get("protocol"):
            return blank_telemetry_attitude()
        try:
            rec = get_global_mavlink_receiver()
            data = rec.fetch_attitude_data() if rec and rec.is_connected() else None
            if data:
                return data
        except Exception as e:
            pass
        # return last_values["attitude"] or blank_telemetry_attitude() # This line is removed as per new_code
        return blank_telemetry_attitude()


class BatteryDataFetcher(TelemetryDataFetcher):
    """Battery status data fetcher"""
    
    def fetch_battery_data(self) -> Dict[str, Any]:
        """
        Fetch battery data from hardware.
        
        TODO: Implement actual battery monitoring:
        - Connect to battery management system (BMS)
        - Read voltage, current, temperature sensors
        - Calculate capacity and health metrics
        
        Example implementations:
        - ADC voltage/current sensors: Use ADS1115 or similar
        - I2C battery monitor: Use MAX17048 or similar
        - Custom BMS: Implement your specific protocol
        """
        if not telemetry_connection_settings.get("protocol"):
            return blank_telemetry_battery()
        try:
            rec = get_global_mavlink_receiver()
            data = rec.fetch_battery_data() if rec and rec.is_connected() else None
            if data:
                return data
        except Exception as e:
            pass
        # return last_values["battery"] or blank_telemetry_battery() # This line is removed as per new_code
        return blank_telemetry_battery()


class FlightDataFetcher(TelemetryDataFetcher):
    """VFR_HUD message data fetcher"""
    
    def fetch_flight_data(self) -> Dict[str, Any]:
        """
        Fetch VFR_HUD data from MAVLink.
        
        TODO: Implement actual VFR_HUD data fetching from MAVLink:
        - Connect to MAVLink stream (UDP, TCP, Serial)
        - Listen for VFR_HUD messages
        - Parse and return structured VFR_HUD data
        
        Example implementation:
        from pymavlink import mavutil
        master = mavutil.mavlink_connection('udpin:localhost:14550')
        msg = master.recv_match(type='VFR_HUD', blocking=True)
        if msg:
            return {
                "airspeed": msg.airspeed,
                "groundspeed": msg.groundspeed,
                "heading": msg.heading,
                "throttle": msg.throttle,
                "alt": msg.alt,
                "climb": msg.climb,
                "timestamp": datetime.now()
            }
        """
        if not telemetry_connection_settings.get("protocol"):
            return blank_telemetry_vfr_hud()
        try:
            rec = get_global_mavlink_receiver()
            data = rec.fetch_vfrhud_data() if rec and rec.is_connected() else None
            if data:
                return data
        except Exception as e:
            pass
        # return last_values["vfr_hud"] or blank_telemetry_vfr_hud() # This line is removed as per new_code
        return blank_telemetry_vfr_hud()


class SystemStatusFetcher(TelemetryDataFetcher):
    """System health and status data fetcher"""
    
    def fetch_system_status(self) -> Dict[str, Any]:
        """
        Fetch system status data.
        
        TODO: Implement actual system monitoring:
        - Read CPU, memory, disk usage
        - Monitor temperature sensors
        - Check network connectivity
        - Track system uptime
        
        Example implementations:
        - psutil for system metrics
        - GPIO temperature sensors
        - Network connectivity checks
        """
        if not telemetry_connection_settings.get("protocol"):
            return blank_telemetry_system()
        try:
            rec = get_global_mavlink_receiver()
            data = rec.fetch_system_status() if rec and rec.is_connected() else None
            if data:
                return data
        except Exception as e:
            pass
        # return last_values["system"] or blank_telemetry_system() # This line is removed as per new_code
        return blank_telemetry_system()


class TelemetryManager:
    """
    Manages telemetry data fetching for a session.
    This is the main class to use for telemetry data management.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self.fetchers = {
            "gps": GPSDataFetcher(session_id),
            "attitude": IMUDataFetcher(session_id),  # Using IMUDataFetcher for attitude data
            "vfr_hud": FlightDataFetcher(session_id),  # Using FlightDataFetcher for VFR HUD data
            "battery": BatteryDataFetcher(session_id),
            "system": SystemStatusFetcher(session_id)
        }
        self.is_initialized = False
    
    def initialize(self) -> bool:
        """
        Initialize all telemetry data fetchers.
        Returns True if all fetchers initialized successfully.
        """
        try:
            # The fetchers will use get_global_mavlink_receiver() internally
            for name, fetcher in self.fetchers.items():
                if not fetcher.connect():
                    logger.error(f"Failed to connect {name} fetcher")
                    return False
                logger.info(f"Connected {name} fetcher")
            
            self.is_initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize telemetry manager: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown all telemetry data fetchers."""
        for name, fetcher in self.fetchers.items():
            try:
                fetcher.disconnect()
                logger.info(f"Disconnected {name} fetcher")
            except Exception as e:
                logger.error(f"Error disconnecting {name} fetcher: {e}")
        
        self.is_initialized = False

    def fetch_all_data(self) -> Dict[str, Any]:
        """Fetch all data from the telemetry fetchers."""
        if not self.is_initialized:
            # Fallback to blank data if not connected
            return {
                "gps": blank_telemetry_gps(),
                "attitude": blank_telemetry_attitude(),
                "vfr_hud": blank_telemetry_vfr_hud(),
                "battery": blank_telemetry_battery(),
                "system": blank_telemetry_system(),
                "status": blank_telemetry_status(),
            }
        
        data: Dict[str, Any] = {}
        for name, fetcher in self.fetchers.items():
            try:
                if name == "gps":
                    data["gps"] = fetcher.fetch_gps_data()
                elif name == "attitude":
                    data["attitude"] = fetcher.fetch_imu_data()
                elif name == "vfr_hud":
                    data["vfr_hud"] = fetcher.fetch_flight_data()
                elif name == "battery":
                    data["battery"] = fetcher.fetch_battery_data()
                elif name == "system":
                    data["system"] = fetcher.fetch_system_status()
            except Exception as e:
                logger.error(f"Error fetching {name} data: {e}")
                # Provide blanks if an error occurs for a sensor
                if name == "gps":
                    data["gps"] = blank_telemetry_gps()
                elif name == "attitude":
                    data["attitude"] = blank_telemetry_attitude()
                elif name == "vfr_hud":
                    data["vfr_hud"] = blank_telemetry_vfr_hud()
                elif name == "battery":
                    data["battery"] = blank_telemetry_battery()
                elif name == "system":
                    data["system"] = blank_telemetry_system()
                # Continue with other fetchers even if one fails
        
        # Fetch armed/mode status from heartbeat
        try:
            if telemetry_connection_settings.get("protocol"):
                rec = get_global_mavlink_receiver()
                status = rec.fetch_status() if rec and rec.is_connected() else None
                data["status"] = status if status else blank_telemetry_status()
            else:
                data["status"] = blank_telemetry_status()
        except Exception as e:
            logger.error(f"Error fetching status: {e}")
            data["status"] = blank_telemetry_status()

        data["session_id"] = self.session_id
        data["timestamp"] = datetime.now().isoformat()
        return data
    
    def fetch_sensor_data(self, sensor_name: str) -> Dict[str, Any]:
        """
        Fetch data from a specific sensor.
        Returns data from the specified sensor.
        """
        if not self.is_initialized:
            raise RuntimeError("TelemetryManager not initialized")
        
        if sensor_name not in self.fetchers:
            raise ValueError(f"Unknown sensor: {sensor_name}")
        
        fetcher = self.fetchers[sensor_name]
        
        if sensor_name == "gps":
            return fetcher.fetch_gps_data()
        elif sensor_name == "attitude":
            return fetcher.fetch_imu_data()
        elif sensor_name == "vfr_hud":
            return fetcher.fetch_flight_data()
        elif sensor_name == "battery":
            return fetcher.fetch_battery_data()
        elif sensor_name == "system":
            return fetcher.fetch_system_status()
        else:
            raise ValueError(f"Unknown sensor: {sensor_name}")


def get_telemetry_manager(session_id: Optional[str] = None, force_new: bool = False) -> "TelemetryManager":
    """
    Get the singleton instance of the TelemetryManager.
    Creates it if it doesn't exist or if a new instance is forced.
    """
    global _telemetry_manager_instance
    if _telemetry_manager_instance is None or force_new:
        if _telemetry_manager_instance:
            # If forcing new, ensure the old one is shut down first
            _telemetry_manager_instance.shutdown()
            
        _telemetry_manager_instance = TelemetryManager(session_id)
        if not _telemetry_manager_instance.initialize():
             logger.error("Failed to initialize telemetry manager")
             raise RuntimeError("Failed to initialize telemetry manager")
             
    return _telemetry_manager_instance


def shutdown_telemetry_manager():
    """Shutdown the global telemetry manager."""
    global _telemetry_manager_instance
    
    if _telemetry_manager_instance is not None:
        _telemetry_manager_instance.shutdown()
        _telemetry_manager_instance = None
