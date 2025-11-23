import time
import logging
import threading
import json
import asyncio
from typing import Optional
from pymavlink import mavutil
from swarm_manager import SwarmManager

logger = logging.getLogger(__name__)

class MissionController:
    def __init__(self, swarm_manager: SwarmManager, connection_manager=None):
        self.swarm_manager = swarm_manager
        self.connection_manager = connection_manager
        self.is_responding = False
        self.lock = threading.Lock()
    
    def _broadcast_event(self, event_type: str, message: str):
        """Broadcast mission event to WebSocket clients"""
        if self.connection_manager:
            event = {
                "type": "mission_event",
                "event_type": event_type,
                "message": message,
                "timestamp": time.time()
            }
            try:
                asyncio.run(self.connection_manager.broadcast(json.dumps(event)))
            except Exception as e:
                logger.error(f"Failed to broadcast event: {e}")

    def trigger_disaster_response(self, sys_id: int):
        """
        Execute the disaster response sequence:
        1. Pause Mission (GUIDED)
        2. Descend to 0.5m
        3. Drop Payload
        4. Ascend
        5. Resume Mission (AUTO)
        """
        with self.lock:
            if self.is_responding:
                logger.warning(f"MissionController: Already responding to disaster on drone {sys_id}")
                return
            self.is_responding = True

        threading.Thread(target=self._response_sequence, args=(sys_id,), daemon=True).start()

    def _response_sequence(self, sys_id: int):
        try:
            logger.info(f"STARTING DISASTER RESPONSE FOR DRONE {sys_id}")
            self._broadcast_event("disaster_response", f"Starting disaster response for drone {sys_id}")
            
            # Get drone agent
            agent = self.swarm_manager.get_drone(sys_id)
            if not agent or not agent.master:
                logger.error(f"Drone {sys_id} not found or not connected")
                self._broadcast_event("error", f"Drone {sys_id} not found or not connected")
                return

            master = agent.master
            original_alt = agent.status.altitude_m or 10.0

            # 1. Switch to GUIDED (Pause Mission)
            logger.info("1. Switching to GUIDED mode...")
            self._broadcast_event("navigation", "Switching to GUIDED mode")
            self._set_mode(master, 'GUIDED')
            time.sleep(2)

            # 2. Descend to 0.5m
            logger.info("2. Descending to 0.5m...")
            self._broadcast_event("navigation", "Descending to 0.5m")
            self._goto_position_target_local_ned(master, 0, 0, 0.5) # Down is positive in NED, but using global alt command is safer
            # Alternative: Use MAV_CMD_NAV_WAYPOINT with current lat/lon and 0.5m alt
            # For simplicity in GUIDED, we often use set_position_target_global_int
            
            # Let's use a simple takeoff command but with low altitude? No, that's for takeoff.
            # Use SET_POSITION_TARGET_GLOBAL_INT
            current_lat = int(agent.status.latitude_deg * 1e7)
            current_lon = int(agent.status.longitude_deg * 1e7)
            
            master.mav.set_position_target_global_int_send(
                0, # time_boot_ms
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                0b0000111111111000, # type_mask (only x, y, z valid)
                current_lat,
                current_lon,
                0.5, # altitude (meters)
                0, 0, 0, # velocity
                0, 0, 0, # accel
                0, 0 # yaw, yaw_rate
            )
            
            # Wait for descent (simple timeout for now, ideally check altitude)
            time.sleep(10) 

            # 3. Drop Payload (Servo)
            logger.info("3. Dropping Payload...")
            self._broadcast_event("navigation", "Dropping payload")
            # Assume Servo 1 (Channel 9)
            self._set_servo(master, 9, 2000) # Open
            time.sleep(2)
            self._set_servo(master, 9, 1000) # Close
            time.sleep(1)

            # 4. Ascend to original altitude
            logger.info(f"4. Ascending to {original_alt}m...")
            self._broadcast_event("navigation", f"Ascending to {original_alt}m")
            master.mav.set_position_target_global_int_send(
                0,
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                0b0000111111111000,
                current_lat,
                current_lon,
                original_alt,
                0, 0, 0,
                0, 0, 0,
                0, 0
            )
            time.sleep(8)

            # 5. Resume Mission (AUTO)
            logger.info("5. Resuming AUTO mission...")
            self._broadcast_event("navigation", "Resuming AUTO mission")
            self._set_mode(master, 'AUTO')

            logger.info("DISASTER RESPONSE COMPLETED")
            self._broadcast_event("disaster_response", "Disaster response completed successfully")

        except Exception as e:
            logger.error(f"Disaster response failed: {e}")
        finally:
            with self.lock:
                self.is_responding = False

    def _set_mode(self, master, mode_name):
        mode_id = master.mode_mapping().get(mode_name)
        if mode_id is None:
            logger.error(f"Mode {mode_name} not found")
            return
        master.mav.set_mode_send(
            master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

    def _set_servo(self, master, channel, pwm):
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            0,
            channel,
            pwm,
            0, 0, 0, 0, 0
        )

    def _goto_position_target_local_ned(self, master, x, y, z):
        # Placeholder for local NED movement if needed
        pass
