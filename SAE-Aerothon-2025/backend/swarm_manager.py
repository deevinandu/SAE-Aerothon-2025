import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from pymavlink import mavutil


logger = logging.getLogger("swarm_manager")


@dataclass
class DroneStatus:
    """Lightweight snapshot of the latest known vehicle state."""

    sys_id: int
    connected: bool = False
    last_heartbeat_s: float = 0.0
    flight_mode: str = "UNKNOWN"
    armed: Optional[bool] = None
    battery_remaining: Optional[float] = None
    battery_voltage: Optional[float] = None
    latitude_deg: Optional[float] = None
    longitude_deg: Optional[float] = None
    altitude_m: Optional[float] = None
    groundspeed_m_s: Optional[float] = None
    # GPS data
    gps_satellites: Optional[int] = None
    gps_heading: Optional[float] = None  # Course over ground
    gps_speed: Optional[float] = None  # GPS speed
    gps_fix_type: Optional[int] = None
    # Attitude data
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    # VFR_HUD data
    vfr_heading: Optional[float] = None
    vfr_airspeed: Optional[float] = None
    vfr_throttle: Optional[float] = None
    vfr_climb: Optional[float] = None


@dataclass
class MissionItem:
    """Container for MISSION_ITEM_INT payload."""

    seq: int
    frame: int
    command: int
    current: int
    autocontinue: int
    param1: float
    param2: float
    param3: float
    param4: float
    x: int  # latitude * 1e7
    y: int  # longitude * 1e7
    z: float  # altitude meters


class DroneAgent:
    """Represents a single UAV on the shared MAVLink connection."""

    def __init__(
        self,
        sys_id: int,
        master: mavutil.mavfile,
        target_component: int = mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1,
    ):
        self.sys_id = sys_id
        self.master = master
        self.target_component = target_component
        self.status = DroneStatus(sys_id=sys_id)
        self._status_lock = threading.Lock()
        self._mission_items: Optional[List[MissionItem]] = None
        self._mission_lock = threading.Lock()
        self._mission_type = mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        self.logger = logging.getLogger(f"DroneAgent[{sys_id}]")
        # Queue for mission-related messages during upload (reader loop puts messages here)
        self._mission_msg_queue: queue.Queue = queue.Queue()
        self._uploading_mission = False  # Flag to indicate we're in upload mode

    # ------------------------------------------------------------------ #
    # Telemetry handling                                                 #
    # ------------------------------------------------------------------ #
    def update_state(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        """Process an incoming MAVLink message originating from this drone."""
        msg_type = msg.get_type()

        if msg_type == "HEARTBEAT":
            self._handle_heartbeat(msg)
        elif msg_type == "SYS_STATUS":
            self._handle_sys_status(msg)
        elif msg_type == "GLOBAL_POSITION_INT":
            self._handle_global_position(msg)
        elif msg_type == "GPS_RAW_INT":
            self._handle_gps_raw_int(msg)
        elif msg_type == "ATTITUDE":
            self._handle_attitude(msg)
        elif msg_type == "VFR_HUD":
            self._handle_vfr_hud(msg)
        elif msg_type in {"MISSION_REQUEST", "MISSION_REQUEST_INT"}:
            # If we're uploading, put message in queue for synchronous handler
            if self._uploading_mission:
                try:
                    self._mission_msg_queue.put_nowait(msg)
                except queue.Full:
                    self.logger.warning("Mission message queue full, dropping message")
            else:
                # Otherwise use async handler
                self._handle_mission_request(msg)
        elif msg_type == "MISSION_ACK":
            # If we're uploading, put message in queue for synchronous handler
            try:
                ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name if hasattr(mavutil.mavlink, 'enums') and 'MAV_MISSION_RESULT' in mavutil.mavlink.enums else str(msg.type)
            except (KeyError, AttributeError):
                ack_type_name = str(msg.type)
            
            self.logger.info("[MISSION_ACK] Received MISSION_ACK: type=%d (%s), uploading=%s, sys_id=%d", 
                            msg.type, ack_type_name, self._uploading_mission, self.sys_id)
            
            if self._uploading_mission:
                try:
                    self._mission_msg_queue.put_nowait(msg)
                    self.logger.info("[MISSION_ACK] Queued MISSION_ACK (type=%d, %s) for synchronous handler", 
                                   msg.type, ack_type_name)
                except queue.Full:
                    self.logger.warning("[MISSION_ACK] Mission message queue full, dropping message")
            else:
                # Not in upload mode - ignore MISSION_ACK messages (they're likely stale from a previous upload)
                self.logger.info("[MISSION_ACK] IGNORING MISSION_ACK (type=%d, %s) - not in upload mode (stale message from drone)", 
                                msg.type, ack_type_name)
                # DO NOT call handler - these are stale messages from previous uploads

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe copy of the latest status."""
        with self._status_lock:
            return asdict(self.status)

    def _handle_heartbeat(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        mode = mavutil.mode_string_v10(msg)
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        with self._status_lock:
            self.status.connected = True
            self.status.last_heartbeat_s = time.time()
            self.status.flight_mode = mode
            self.status.armed = armed

    def _handle_sys_status(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        with self._status_lock:
            self.status.battery_remaining = msg.battery_remaining
            if msg.voltage_battery > 0:
                self.status.battery_voltage = msg.voltage_battery / 1000.0

    def _handle_global_position(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        with self._status_lock:
            self.status.latitude_deg = msg.lat / 1e7
            self.status.longitude_deg = msg.lon / 1e7
            self.status.altitude_m = msg.alt / 1000.0
            # GLOBAL_POSITION_INT also has velocity info
            if hasattr(msg, 'vx') and hasattr(msg, 'vy'):
                # Ground speed from velocity components
                import math
                vx = msg.vx / 100.0  # cm/s to m/s
                vy = msg.vy / 100.0
                self.status.groundspeed_m_s = math.sqrt(vx * vx + vy * vy)

    def _handle_gps_raw_int(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        """Handle GPS_RAW_INT message for satellite count and GPS heading."""
        with self._status_lock:
            self.status.gps_satellites = getattr(msg, 'satellites_visible', None)
            self.status.gps_fix_type = getattr(msg, 'fix_type', None)
            if hasattr(msg, 'cog') and msg.cog != 65535:  # 65535 = invalid
                self.status.gps_heading = msg.cog / 100.0  # Convert from centidegrees
            if hasattr(msg, 'vel') and msg.vel != 65535:  # 65535 = invalid
                self.status.gps_speed = msg.vel / 100.0  # Convert from cm/s to m/s

    def _handle_attitude(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        """Handle ATTITUDE message for roll, pitch, yaw."""
        with self._status_lock:
            self.status.roll = msg.roll
            self.status.pitch = msg.pitch
            self.status.yaw = msg.yaw

    def _handle_vfr_hud(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        with self._status_lock:
            self.status.groundspeed_m_s = msg.groundspeed
            self.status.vfr_airspeed = getattr(msg, 'airspeed', None)
            self.status.vfr_heading = getattr(msg, 'heading', None)
            self.status.vfr_throttle = getattr(msg, 'throttle', None)
            self.status.vfr_climb = getattr(msg, 'climb', None)

    # ------------------------------------------------------------------ #
    # Mission upload logic                                               #
    # ------------------------------------------------------------------ #
    def upload_mission(
        self,
        waypoints: Optional[List[Tuple[float, float, float]]] = None,
        mission_items_override: Optional[List[MissionItem]] = None,
    ) -> None:
        """Upload mission to this drone using synchronous handshake (blocks until complete)."""
        if mission_items_override is None and not waypoints:
            raise ValueError("Either mission_items_override or waypoints must be provided.")
        
        mission_items = mission_items_override or self._build_mission_items(waypoints or [])
        self._mission_items = mission_items

        self.logger.info("Starting mission upload with %d mission items to sys_id=%d.", len(mission_items), self.sys_id)
        waypoint_preview = waypoints[:5] if waypoints else []
        if waypoint_preview:
            self.logger.debug("Waypoint preview: %s", waypoint_preview)

        # Set upload flag and clear queue
        self.logger.debug("[upload_mission] Setting upload flag to True")
        self._uploading_mission = True
        # Clear any old messages from queue
        cleared_count = 0
        while not self._mission_msg_queue.empty():
            try:
                self._mission_msg_queue.get_nowait()
                cleared_count += 1
            except queue.Empty:
                break
        if cleared_count > 0:
            self.logger.debug("[upload_mission] Cleared %d old messages from queue", cleared_count)

        try:
            # Clear any existing mission first
            self.logger.debug("Clearing existing mission on sys_id=%d", self.sys_id)
            self.master.mav.mission_clear_all_send(
                target_system=self.sys_id,
                target_component=self.target_component,
                mission_type=self._mission_type,
            )
            # Wait for clear ACK from queue (reader loop will put it there)
            try:
                clear_ack = self._mission_msg_queue.get(timeout=3)
                if clear_ack.get_type() == 'MISSION_ACK':
                    self.logger.debug("Mission cleared, received ACK type=%d", clear_ack.type)
            except queue.Empty:
                self.logger.warning("Timeout waiting for MISSION_CLEAR_ALL ACK, continuing anyway")

            # Send mission count
            self.logger.info("Sending MISSION_COUNT: count=%d to sys_id=%d", len(mission_items), self.sys_id)
            self.master.mav.mission_count_send(
                target_system=self.sys_id,
                target_component=self.target_component,
                count=len(mission_items),
                mission_type=self._mission_type,
            )

            # Upload each mission item synchronously (wait for request from queue, then send item)
            # Track which items have been sent to handle retries
            items_sent = set()
            expected_seq = 0  # Track the next expected sequence number
            
            while len(items_sent) < len(mission_items):
                # Wait for mission request from queue (reader loop puts it there)
                self.logger.debug("Waiting for MISSION_REQUEST for item %d/%d (sent: %s)", 
                                expected_seq, len(mission_items) - 1, sorted(items_sent))
                msg = None
                start_time = time.time()
                timeout = 5.0
                
                while time.time() - start_time < timeout:
                    try:
                        msg = self._mission_msg_queue.get(timeout=0.1)
                        msg_type = msg.get_type()
                        if msg_type in {'MISSION_REQUEST', 'MISSION_REQUEST_INT'}:
                            requested_seq = msg.seq
                            # Check if this is a valid sequence number
                            if 0 <= requested_seq < len(mission_items):
                                # If we've already sent this item, it's a retry - resend it
                                if requested_seq in items_sent:
                                    self.logger.info("Received MISSION_REQUEST for already-sent seq=%d (retry), resending", requested_seq)
                                break  # Got a valid request
                            else:
                                self.logger.warning("Received MISSION_REQUEST with invalid seq=%d (range 0-%d), ignoring", 
                                                  requested_seq, len(mission_items) - 1)
                                msg = None
                                continue
                        else:
                            # Not a mission request, log and continue waiting
                            self.logger.debug("Received non-MISSION_REQUEST message %s during upload, continuing to wait", msg_type)
                            msg = None  # Reset to continue waiting
                            continue
                    except queue.Empty:
                        continue  # Continue waiting
                
                if msg is None or msg.get_type() not in {'MISSION_REQUEST', 'MISSION_REQUEST_INT'}:
                    self.logger.error("Timeout waiting for mission request (expected seq=%d, sent: %s)", 
                                    expected_seq, sorted(items_sent))
                    raise TimeoutError(f"Timeout waiting for MISSION_REQUEST for item {expected_seq}")
                
                requested_seq = msg.seq
                self.logger.info("Received MISSION_REQUEST: seq=%d (expected next: %d, sent: %s)", 
                               requested_seq, expected_seq, sorted(items_sent))
                
                # Send the item that matches the requested sequence number
                mission_item = mission_items[requested_seq]
                
                # Send the mission item with the requested sequence number
                self.logger.info("Sending MISSION_ITEM_INT: seq=%d, cmd=%d, lat=%d, lon=%d, alt=%.1f",
                               requested_seq, mission_item.command, mission_item.x, mission_item.y, mission_item.z)
                
                self.master.mav.mission_item_int_send(
                    target_system=self.sys_id,
                    target_component=self.target_component,
                    seq=requested_seq,  # Use requested_seq to match what drone expects
                    frame=mission_item.frame,
                    command=mission_item.command,
                    current=mission_item.current,
                    autocontinue=mission_item.autocontinue,
                    param1=mission_item.param1,
                    param2=mission_item.param2,
                    param3=mission_item.param3,
                    param4=mission_item.param4,
                    x=mission_item.x,
                    y=mission_item.y,
                    z=mission_item.z,
                    mission_type=self._mission_type,
                )
                
                items_sent.add(requested_seq)
                
                # Update expected sequence to the next unsent item
                while expected_seq in items_sent and expected_seq < len(mission_items):
                    expected_seq += 1
                
                # If we've sent all items, break
                if len(items_sent) == len(mission_items):
                    self.logger.info("All mission items sent (%s), waiting for final ACK", sorted(items_sent))
                    break

            # Wait for final MISSION_ACK from queue
            self.logger.debug("[upload_mission] Waiting for final MISSION_ACK from queue")
            ack = None
            start_time = time.time()
            timeout = 5.0
            
            while time.time() - start_time < timeout:
                try:
                    msg = self._mission_msg_queue.get(timeout=0.1)
                    self.logger.debug("[upload_mission] Got message from queue: type=%s", msg.get_type())
                    if msg.get_type() == 'MISSION_ACK':
                        ack = msg
                        try:
                            ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][ack.type].name
                        except (KeyError, AttributeError):
                            ack_type_name = str(ack.type)
                        self.logger.debug("[upload_mission] Received MISSION_ACK from queue: type=%d (%s)", 
                                        ack.type, ack_type_name)
                        # If we get ACCEPTED, we're done - don't wait for more ACKs
                        if ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                            self.logger.info("[upload_mission] Mission upload ACCEPTED by drone sys_id=%d", self.sys_id)
                            # Immediately clear upload flag to prevent processing any more ACKs
                            self.logger.info("[upload_mission] Clearing upload flag immediately after ACCEPTED")
                            self._uploading_mission = False
                            # Drain any remaining messages from queue to prevent them from being processed
                            drained_after_accept = 0
                            while not self._mission_msg_queue.empty():
                                try:
                                    remaining_msg = self._mission_msg_queue.get_nowait()
                                    drained_after_accept += 1
                                    if remaining_msg.get_type() == 'MISSION_ACK':
                                        try:
                                            remaining_ack_type = mavutil.mavlink.enums['MAV_MISSION_RESULT'][remaining_msg.type].name
                                        except (KeyError, AttributeError):
                                            remaining_ack_type = str(remaining_msg.type)
                                        self.logger.info("[upload_mission] Drained remaining MISSION_ACK (type=%d, %s) after ACCEPTED - IGNORING", 
                                                        remaining_msg.type, remaining_ack_type)
                                except queue.Empty:
                                    break
                            if drained_after_accept > 0:
                                self.logger.info("[upload_mission] Drained %d remaining messages after ACCEPTED", drained_after_accept)
                            break
                        # If we get an error, log it but continue waiting for ACCEPTED (might be a retry)
                        else:
                            self.logger.warning("[upload_mission] Received MISSION_ACK with type %s (%s), continuing to wait for ACCEPTED", 
                                              ack.type, ack_type_name)
                            ack = None  # Reset to continue waiting
                            continue
                    else:
                        self.logger.debug("[upload_mission] Received non-MISSION_ACK message %s, continuing to wait", msg.get_type())
                        continue
                except queue.Empty:
                    continue
            
            if ack is None or ack.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
                if ack is None:
                    self.logger.error("Timeout waiting for final MISSION_ACK")
                    raise TimeoutError("Timeout waiting for final MISSION_ACK")
                else:
                    # Try to get human-readable error name
                    try:
                        ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][ack.type].name
                    except (KeyError, AttributeError):
                        ack_type_name = str(ack.type)
                    self.logger.error("Mission upload REJECTED by drone sys_id=%d with type %s (%s)", 
                                    self.sys_id, ack.type, ack_type_name)
                    raise RuntimeError(f"Mission upload rejected: {ack_type_name}")
        finally:
            # Always clear upload flag (if not already cleared)
            if self._uploading_mission:
                self.logger.debug("[upload_mission] Clearing upload flag in finally block")
                self._uploading_mission = False
                # Clear any remaining messages from queue (should be empty if we got ACCEPTED)
                drained_count = 0
                while not self._mission_msg_queue.empty():
                    try:
                        msg = self._mission_msg_queue.get_nowait()
                        drained_count += 1
                        if msg.get_type() == 'MISSION_ACK':
                            try:
                                ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name
                            except (KeyError, AttributeError):
                                ack_type_name = str(msg.type)
                            self.logger.debug("[upload_mission] Drained MISSION_ACK (type=%d, %s) from queue in finally", 
                                            msg.type, ack_type_name)
                    except queue.Empty:
                        break
                if drained_count > 0:
                    self.logger.debug("[upload_mission] Drained %d messages from queue in finally block", drained_count)

    def _build_mission_items(self, waypoints: List[Tuple[float, float, float]]) -> List[MissionItem]:
        """Convert lat/lon/alt tuples into MissionItem dataclasses."""
        mission_items: List[MissionItem] = []
        for seq, (lat, lon, alt) in enumerate(waypoints):
            mission_items.append(
                MissionItem(
                    seq=seq,
                    frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    command=mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    current=1 if seq == 0 else 0,
                    autocontinue=1,
                    param1=0,  # hold
                    param2=0,  # acceptance radius
                    param3=0,  # pass through
                    # Use 0 yaw instead of NaN to avoid MAV_MISSION_ERROR responses from some autopilots
                    param4=0.0,
                    x=int(lat * 1e7),
                    y=int(lon * 1e7),
                    z=alt,
                )
            )
        return mission_items

    def arm_and_start_mission(self, takeoff_altitude: float = 30.0) -> bool:
        """
        Arm the vehicle and start the mission.
        Sets mode to GUIDED, arms, takes off, then switches to AUTO.
        
        Args:
            takeoff_altitude: Altitude to take off to (meters)
            
        Returns:
            bool: True if successful, False otherwise
        """
        import time
        
        self.logger.info("Starting mission for drone sys_id=%d (takeoff altitude: %.1fm)", 
                        self.sys_id, takeoff_altitude)
        
        try:
            # Step 1: Set mode to GUIDED
            self.logger.info("Setting flight mode to GUIDED for sys_id=%d", self.sys_id)
            mode_id = self.master.mode_mapping().get('GUIDED')
            if mode_id is None:
                self.logger.error("GUIDED mode not available for sys_id=%d", self.sys_id)
                return False
            
            self.master.mav.set_mode_send(
                self.sys_id,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )
            time.sleep(1)
            self.logger.info("Mode set to GUIDED for sys_id=%d", self.sys_id)
            
            # Step 2: Arm the vehicle
            self.logger.info("Arming vehicle sys_id=%d", self.sys_id)
            # Check if already armed
            with self._status_lock:
                is_armed = self.status.armed
            
            if not is_armed:
                self.master.mav.command_long_send(
                    self.sys_id,
                    self.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0,
                    1, 0, 0, 0, 0, 0, 0
                )
                
                # Wait for arm ACK
                ack = self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
                if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    self.logger.info("Vehicle sys_id=%d armed successfully", self.sys_id)
                    time.sleep(2)
                else:
                    self.logger.error("Failed to arm vehicle sys_id=%d", self.sys_id)
                    return False
            else:
                self.logger.info("Vehicle sys_id=%d already armed", self.sys_id)
            
            # Step 3: Command takeoff in GUIDED mode
            self.logger.info("Taking off to %.1fm for sys_id=%d", takeoff_altitude, self.sys_id)
            self.master.mav.command_long_send(
                self.sys_id,
                self.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0,
                0,  # param1: pitch
                0,  # param2: empty
                0,  # param3: empty
                0,  # param4: yaw
                0,  # param5: latitude (0 = current position)
                0,  # param6: longitude (0 = current position)
                takeoff_altitude  # param7: altitude
            )
            
            ack = self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                self.logger.info("Takeoff command accepted for sys_id=%d", self.sys_id)
            else:
                self.logger.warning("Takeoff command may have failed for sys_id=%d, but continuing...", self.sys_id)
            
            # Wait for takeoff to complete
            self.logger.info("Waiting for takeoff to complete for sys_id=%d...", self.sys_id)
            time.sleep(8)  # Give it time to climb
            
            # Step 4: Switch to AUTO mode to execute the mission
            self.logger.info("Setting flight mode to AUTO to start mission for sys_id=%d", self.sys_id)
            mode_id = self.master.mode_mapping().get('AUTO')
            if mode_id is None:
                self.logger.error("AUTO mode not available for sys_id=%d", self.sys_id)
                return False
            
            self.master.mav.set_mode_send(
                self.sys_id,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )
            time.sleep(1)
            self.logger.info("Mode set to AUTO for sys_id=%d - mission started!", self.sys_id)
            
            return True
            
        except Exception as exc:
            self.logger.error("Error starting mission for sys_id=%d: %s", self.sys_id, exc, exc_info=True)
            return False

    def _handle_mission_request(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        """Respond to mission item requests as part of the upload handshake."""
        # MISSION_REQUEST messages come FROM the drone (srcSystem = drone's sys_id)
        # The reader loop already routes messages to the correct agent based on srcSystem,
        # so by the time we get here, this message is already for this drone
        with self._mission_lock:
            if not self._mission_items:
                self.logger.warning("Received mission request but no mission queued for sys_id=%d.", self.sys_id)
                return

            requested_seq = msg.seq
            self.logger.info("Received MISSION_REQUEST: seq=%d for sys_id=%d (have %d items)", 
                           requested_seq, self.sys_id, len(self._mission_items))
            
            if requested_seq >= len(self._mission_items):
                self.logger.error("Requested mission seq %s outside range (have %d items) for sys_id=%d.", 
                                requested_seq, len(self._mission_items), self.sys_id)
                return

            mission_item = self._mission_items[requested_seq]
            
            # Ensure the sequence number in the response matches what was requested
            self.logger.info("Sending MISSION_ITEM_INT: seq=%d, cmd=%d, lat=%d, lon=%d, alt=%.1f for sys_id=%d",
                           requested_seq, mission_item.command, mission_item.x, mission_item.y, mission_item.z, self.sys_id)
            
            self.master.mav.mission_item_int_send(
                target_system=self.sys_id,  # ensure only this system accepts the item
                target_component=self.target_component,
                seq=requested_seq,  # Use requested_seq to ensure it matches what drone expects
                frame=mission_item.frame,
                command=mission_item.command,
                current=mission_item.current,
                autocontinue=mission_item.autocontinue,
                param1=mission_item.param1,
                param2=mission_item.param2,
                param3=mission_item.param3,
                param4=mission_item.param4,
                x=mission_item.x,
                y=mission_item.y,
                z=mission_item.z,
                mission_type=self._mission_type,
            )

    def _handle_mission_ack(self, msg: mavutil.mavlink.MAVLink_message) -> None:
        """Clear mission context after successful upload."""
        # MISSION_ACK messages come FROM the drone (srcSystem = drone's sys_id)
        # The reader loop already routes messages to the correct agent based on srcSystem,
        # so by the time we get here, this message is already for this drone
        
        self.logger.debug("[_handle_mission_ack] Handler called: type=%d, uploading=%s", 
                        msg.type, self._uploading_mission)
        
        # This handler should only be called when not in upload mode (during async uploads)
        # If we're in upload mode, messages go to the queue instead
        # If we're not in upload mode, these are likely stale messages from a previous upload
        if not self._uploading_mission:
            # Not in upload mode - ignore stale MISSION_ACK messages
            try:
                ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name if hasattr(mavutil.mavlink, 'enums') and 'MAV_MISSION_RESULT' in mavutil.mavlink.enums else str(msg.type)
            except (KeyError, AttributeError):
                ack_type_name = str(msg.type)
            self.logger.debug("[_handle_mission_ack] Ignoring stale MISSION_ACK (type=%d, %s) - not in upload mode", 
                            msg.type, ack_type_name)
            return
        
        ack_type_name = mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name if hasattr(mavutil.mavlink, 'enums') and 'MAV_MISSION_RESULT' in mavutil.mavlink.enums else str(msg.type)
        
        if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            self.logger.info("[_handle_mission_ack] Mission upload ACCEPTED by drone sys_id=%d", self.sys_id)
        else:
            self.logger.error("[_handle_mission_ack] Mission upload REJECTED by drone sys_id=%d with type %s (%s)", 
                            self.sys_id, msg.type, ack_type_name)

        with self._mission_lock:
            self._mission_items = None


class SwarmManager:
    """Swarm-level MAVLink manager that supports multiple connection ports (one per drone/receiver)."""

    def __init__(
        self,
        connection_strings: List[str],
        *,
        baud: int = 115200,
        source_system: int = 255,
    ):
        """
        Initialize SwarmManager with multiple connection strings.
        
        Args:
            connection_strings: List of connection strings (e.g., ["udp:127.0.0.1:14550", "udp:127.0.0.1:14551"])
            baud: Baud rate for serial connections (ignored for UDP/TCP)
            source_system: Source system ID for this GCS
        """
        if not connection_strings:
            raise ValueError("At least one connection string is required")
        
        self.connection_strings = connection_strings
        self._connections: List[Tuple[str, mavutil.mavfile]] = []
        self._agents: Dict[int, DroneAgent] = {}
        self._agents_lock = threading.Lock()
        self._sysid_to_master: Dict[int, mavutil.mavfile] = {}  # Track which master to use for each sys_id
        self._running = False
        self._reader_threads: List[threading.Thread] = []

        # Create MAVLink connections for each connection string
        for conn_str in connection_strings:
            try:
                master = mavutil.mavlink_connection(
                    conn_str,
                    baud=baud,
                    source_system=source_system,
                )
                self._connections.append((conn_str, master))
                logger.info(f"Created MAVLink connection: {conn_str}")
            except Exception as exc:
                logger.error(f"Failed to create connection {conn_str}: {exc}")
                raise

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Start reader threads for all connections."""
        if self._running:
            return
        self._running = True
        
        # Start a reader thread for each connection
        for conn_str, master in self._connections:
            thread = threading.Thread(
                target=self._reader_loop,
                args=(conn_str, master),
                daemon=True,
            )
            thread.start()
            self._reader_threads.append(thread)
            logger.info(f"Started reader thread for connection: {conn_str}")
        
        logger.info(f"SwarmManager started with {len(self._connections)} connection(s)")

    def stop(self) -> None:
        """Stop all reader threads."""
        self._running = False
        for thread in self._reader_threads:
            thread.join(timeout=2)
        self._reader_threads.clear()
        
        # Close all MAVLink connections to release UDP ports
        for conn_str, master in self._connections:
            try:
                master.close()
                logger.info("Closed MAVLink connection: %s", conn_str)
            except Exception as exc:
                logger.warning("Error closing MAVLink connection %s: %s", conn_str, exc)
        self._connections.clear()
        
        # Reset agent mappings so a fresh start() gets clean state
        with self._agents_lock:
            self._agents.clear()
            self._sysid_to_master.clear()
        
        logger.info("SwarmManager stopped")

    def _reader_loop(self, conn_str: str, master: mavutil.mavfile) -> None:
        """Continuously read MAVLink messages from a specific connection and dispatch to the appropriate agent."""
        logger.debug(f"Reader loop started for {conn_str}")
        while self._running:
            try:
                msg = master.recv_match(blocking=True, timeout=1)
            except Exception as exc:
                logger.error(f"Error reading MAVLink from {conn_str}: {exc}")
                continue

            if msg is None:
                continue

            sys_id = msg.get_srcSystem()
            if sys_id == 0:
                continue

            msg_type = msg.get_type()
            # Log mission-related messages for debugging
            if msg_type in {"MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"}:
                logger.debug(f"Reader loop: Received {msg_type} from sys_id={sys_id} on {conn_str}")

            agent = self._get_or_create_agent(sys_id, master)
            agent.update_state(msg)

    def _get_or_create_agent(self, sys_id: int, master: mavutil.mavfile) -> DroneAgent:
        """Get or create a DroneAgent for the given sys_id, tracking which master to use."""
        with self._agents_lock:
            if sys_id not in self._agents:
                logger.info(f"Discovered new drone with sys_id={sys_id}")
                self._agents[sys_id] = DroneAgent(sys_id=sys_id, master=master)
                # Track which master connection discovered this sys_id (for sending commands)
                self._sysid_to_master[sys_id] = master
            return self._agents[sys_id]

    def get_fleet_snapshot(self) -> Dict[int, Dict[str, Any]]:
        """Return a snapshot of the current fleet telemetry."""
        with self._agents_lock:
            return {
                sys_id: agent.get_status_snapshot()
                for sys_id, agent in self._agents.items()
            }

    def send_command(self, sys_id: int, command_type: str, data: Optional[Dict[str, Any]] = None) -> Any:
        """Route user commands to the appropriate drone agent."""
        with self._agents_lock:
            agent = self._agents.get(sys_id)
            if not agent:
                raise KeyError(f"No drone with sys_id {sys_id} is currently connected.")
            
            # Use the master that discovered this sys_id for sending commands
            # This ensures commands go through the correct connection/port
            master = self._sysid_to_master.get(sys_id)
            if not master:
                # Fallback: use the agent's master
                master = agent.master

        if command_type == "upload_mission":
            waypoints = (data or {}).get("waypoints")
            mission_items = (data or {}).get("mission_items")
            # Temporarily update agent's master to use the correct connection
            original_master = agent.master
            agent.master = master
            try:
                agent.upload_mission(waypoints=waypoints, mission_items_override=mission_items)
            finally:
                agent.master = original_master
        elif command_type == "arm_and_start_mission":
            takeoff_altitude = (data or {}).get("takeoff_altitude", 30.0)
            # Temporarily update agent's master to use the correct connection
            original_master = agent.master
            agent.master = master
            try:
                return agent.arm_and_start_mission(takeoff_altitude)
            finally:
                agent.master = original_master
        else:
            raise ValueError(f"Unsupported command type: {command_type}")


# ---------------------------------------------------------------------- #
# Utility helpers                                                       #
# ---------------------------------------------------------------------- #
def parse_kml_coordinates(path: str) -> List[Tuple[float, float, float]]:
    """Parse a minimal KML file to extract (lat, lon, alt) tuples."""
    kml_file = Path(path)
    if not kml_file.exists():
        logger.warning("KML file %s does not exist.", path)
        return []

    content = kml_file.read_text(encoding="utf-8")
    coordinates: List[Tuple[float, float, float]] = []
    for lon, lat, alt in re.findall(r"(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+)", content):
        coordinates.append((float(lat), float(lon), float(alt)))
    return coordinates


def pretty_print_snapshot(snapshot: Dict[int, Dict[str, Any]]) -> None:
    """Render telemetry side-by-side for quick CLI observation."""
    if not snapshot:
        print("No drones detected yet.")
        return

    header = f"{'SYSID':<6} {'MODE':<12} {'LAT':<11} {'LON':<11} {'ALT(m)':<8} {'BAT(%)':<7}"
    print(header)
    print("-" * len(header))
    for sys_id, data in snapshot.items():
        print(
            f"{sys_id:<6} "
            f"{data.get('flight_mode',''): <12} "
            f"{(data.get('latitude_deg') or 0):<11.6f} "
            f"{(data.get('longitude_deg') or 0):<11.6f} "
            f"{(data.get('altitude_m') or 0):<8.1f} "
            f"{(data.get('battery_remaining') or 0):<7}"
        )


# ---------------------------------------------------------------------- #
# Demonstration entry point                                             #
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Support multiple connection URIs (comma-separated or space-separated)
    connection_uris_str = os.getenv("MAVLINK_FLEET_URIS", "udp:127.0.0.1:14550 udp:127.0.0.1:14551")
    connection_uris = [uri.strip() for uri in connection_uris_str.replace(",", " ").split() if uri.strip()]
    mission_kml = os.getenv("MISSION_KML_PATH", str(Path(__file__).with_name("path3.kml")))

    logger.info(f"Initializing SwarmManager with connections: {connection_uris}")
    fleet = SwarmManager(connection_uris)
    fleet.start()

    try:
        logger.info("Waiting for at least two drones to announce themselves...")
        wait_deadline = time.time() + 30
        while time.time() < wait_deadline:
            snapshot = fleet.get_fleet_snapshot()
            if len(snapshot) >= 2:
                break
            time.sleep(1)

        for _ in range(10):
            pretty_print_snapshot(fleet.get_fleet_snapshot())
            time.sleep(1)

        waypoints = parse_kml_coordinates(mission_kml)
        if not waypoints:
            logger.error("No waypoints found in KML file: %s", mission_kml)
            logger.info("Exiting demo - please provide a valid KML file with coordinates.")
        else:
            logger.info("Uploading mission to Drone #2.")
            fleet.send_command(2, "upload_mission", {"waypoints": waypoints})
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        fleet.stop()

