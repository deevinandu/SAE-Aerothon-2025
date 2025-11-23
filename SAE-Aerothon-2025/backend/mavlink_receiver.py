"""
MAVLink Receiver - Generic, supports UDP/TCP/Serial
Receives telemetry using pymavlink using provided connection settings.
Return structured dicts matching the format used everywhere else.
"""
from typing import Optional, Dict, Any, Literal
from pymavlink import mavutil
import time
import logging
from telemetry_config import AC_MODES
import threading

logger = logging.getLogger(__name__)

class MavlinkReceiver:
    def __init__(self, settings: dict):
        """Initialize the MAVLink receiver."""
        self.protocol = (settings.get("protocol") or "").upper()
        self.host = settings.get("host")
        self.port = settings.get("port")
        # For SERIAL protocol, 'port' field contains the serial port path
        self.serial_port = settings.get("serial_port") or (settings.get("port") if self.protocol == "SERIAL" else None)
        self.baud = settings.get("baud") or 57600
        self.master: Optional[mavutil.mavlink_connection] = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.last_messages = {}
        self.last_heartbeat = None
        self.last_heartbeat_ts = 0.0
        self.connected = False
        
        # Start the connection thread immediately
        self.connect()

    def connect(self) -> bool:
        """
        Try to connect to the MAVLink device/source. Returns True if successful.
        """
        try:
            if self.protocol == 'UDP':
                address = f'udpin:{self.host or "127.0.0.1"}:{self.port or 14550}'
            elif self.protocol == 'TCP':
                address = f'tcpin:{self.host or "127.0.0.1"}:{self.port or 5760}'
            elif self.protocol == 'SERIAL':
                address = self.serial_port or "/dev/ttyUSB0"
            else:
                raise ValueError(f"Unsupported protocol: {self.protocol}")

            if self.protocol in ["UDP", "TCP"]:
                self.master = mavutil.mavlink_connection(address, baud=self.baud, input=True)
            else:
                # For SERIAL, use direct connection without input flag
                self.master = mavutil.mavlink_connection(address, baud=self.baud)
            # Serial connections may need more time for initial heartbeat
            timeout = 10.0 if self.protocol == "SERIAL" else 2.0
            self.master.wait_heartbeat(timeout=timeout)
            self.connected = True

            # Request data streams for common telemetry at 5 Hz
            try:
                for stream_id in (
                    mavutil.mavlink.MAV_DATA_STREAM_ALL,
                    mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
                    mavutil.mavlink.MAV_DATA_STREAM_EXTRA1,
                    mavutil.mavlink.MAV_DATA_STREAM_EXTRA2,
                    mavutil.mavlink.MAV_DATA_STREAM_POSITION,
                ):
                    self.master.mav.request_data_stream_send(
                        self.master.target_system,
                        self.master.target_component,
                        stream_id,
                        5,  # Hz
                        1,  # start
                    )
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MAVLink: {e}")
            self.connected = False
            self.master = None
            return False

    def disconnect(self) -> None:
        """
        Disconnect the receiver and clean resources.
        """
        try:
            self.master = None
            self.connected = False
        except Exception:
            pass

    def is_connected(self) -> bool:
        """
        Return True if connected.
        """
        return self.connected

    def _recv_msg(self, msg_type: str) -> Optional[Any]:
        """
        Try to receive a single message of a given type from the link. Returns None if not received.
        """
        if not self.master or not self.connected:
            return None
        # Poll a few times quickly to increase the chance of receiving without blocking
        for _ in range(10):
            msg = self.master.recv_match(type=msg_type, blocking=False)
            if msg is not None:
                if msg_type == 'HEARTBEAT':
                    self.last_heartbeat = msg
                    self.last_heartbeat_ts = time.time()
                return msg
            time.sleep(0.02)
        return None

    def fetch_gps_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch GPS telemetry (GPS_RAW_INT message).
        Returns dict, or None if no data.
        """
        msg = self._recv_msg('GPS_RAW_INT')
        if msg is None:
            return None
        return {
            "latitude": msg.lat / 1e7,
            "longitude": msg.lon / 1e7,
            "altitude": msg.alt / 1000,
            "speed": msg.vel / 100,
            "heading": msg.cog / 100,
            "fix_type": msg.fix_type,
            "satellites": msg.satellites_visible,
            "timestamp": time.time(),
        }

    def fetch_attitude_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch ATTITUDE message.
        """
        msg = self._recv_msg('ATTITUDE')
        if msg is None:
            return None
        return {
            "roll": msg.roll,
            "pitch": msg.pitch,
            "yaw": msg.yaw,
            "rollspeed": msg.rollspeed,
            "pitchspeed": msg.pitchspeed,
            "yawspeed": msg.yawspeed,
            "timestamp": time.time(),
        }

    def fetch_vfrhud_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch VFR_HUD message.
        """
        msg = self._recv_msg('VFR_HUD')
        if msg is None:
            return None
        return {
            "airspeed": msg.airspeed,
            "groundspeed": msg.groundspeed,
            "heading": msg.heading,
            "throttle": msg.throttle,
            "alt": msg.alt,
            "climb": msg.climb,
            "timestamp": time.time(),
        }

    def fetch_battery_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch BATTERY_STATUS message.
        """
        msg = self._recv_msg('BATTERY_STATUS')
        if msg is None:
            return None
        voltage = msg.voltages[0] / 1000 if msg.voltages[0] is not None else 0
        current = msg.current_battery / 100 if hasattr(msg, "current_battery") and msg.current_battery is not None else 0
        remaining = msg.battery_remaining if hasattr(msg, "battery_remaining") else 0
        return {
            "voltage": voltage,
            "current": current,
            "remaining": remaining,
            "timestamp": time.time(),
        }

    def fetch_system_status(self) -> Optional[Dict[str, Any]]:
        """
        Fetch SYS_STATUS message.
        """
        msg = self._recv_msg('SYS_STATUS')
        if msg is None:
            return None
        return {
            "onboard_control_sensors_present": msg.onboard_control_sensors_present,
            "onboard_control_sensors_enabled": msg.onboard_control_sensors_enabled,
            "onboard_control_sensors_health": msg.onboard_control_sensors_health,
            "load": msg.load / 10,
            "voltage_battery": msg.voltage_battery / 1000,
            "current_battery": msg.current_battery / 100,
            "battery_remaining": msg.battery_remaining,
            "timestamp": time.time(),
        }

    def fetch_status(self) -> dict:
        msg = self._recv_msg('HEARTBEAT')
        if msg is None and self.last_heartbeat is not None and (time.time() - self.last_heartbeat_ts) < 5.0:
            msg = self.last_heartbeat
        if msg is None:
            return None
        armed = bool(msg.base_mode & 0b10000000) if hasattr(msg, 'base_mode') else False
        mode_number = getattr(msg, "custom_mode", -1)
        mode_string = AC_MODES.get(mode_number, str(mode_number))
        return {
            "armed": armed,
            "mode": mode_string
        }

    def get_connection(self) -> Optional[mavutil.mavlink_connection]:
        """Return the underlying mavlink connection object."""
        return self.master

    def stop(self):
        """Stop the MAVLink connection."""
        self.running = False
