#!/usr/bin/env python3
"""
Path Creation with MAVLink Integration
This module generates optimized surveillance paths and converts them to MAVLink mission commands.
"""

from pymavlink import mavutil
from shapely.geometry import Point, LineString, Polygon as ShapelyPolygon
import argparse
import sys
import matplotlib.pyplot as plt

# Import path creation functions
# Import path creation functions
from path_planner import (
    load_kml_boundary,
    Polygon,
    choose_best_entry_point,
    choose_best_overlap,
    compute_path_metrics,
    prune_path_by_coverage_barrier,
    prune_return_with_low_gain,
    shortcut_redundant_waypoints,
    trim_redundant_tail
)


# ============================================================================
# CONFIGURATION PARAMETERS - EDIT THESE FOR YOUR MISSION
# ============================================================================

# KML File Configuration
KML_FILE = 'kml/path2.kml'  # Path to your KML geofence file

# UAV Starting Position
USE_DRONE_POSITION = True   # If True, fetch current position from connected drone
UAV_START_LAT = -35.3       # Starting latitude (used only if USE_DRONE_POSITION = False)
UAV_START_LON = 149.1       # Starting longitude (used only if USE_DRONE_POSITION = False)

# Flight Parameters
FLIGHT_ALTITUDE = 50    # Flight altitude in meters
FLIGHT_SPEED = 5.0      # Flight speed in m/s

# Camera/Sensor Parameters
SENSOR_WIDTH = 30       # Sensor footprint width in meters
OVERLAP = 0.2           # Overlap percentage (0.2 = 20%)

# MAVLink Connection (for ArduPilot SITL)
MAVLINK_CONNECTION = 'udp:127.0.0.1:14550'  # SITL default connection string
# Other common connection strings:
# MAVLINK_CONNECTION = 'tcp:127.0.0.1:5762'  # Alternative SITL
# MAVLINK_CONNECTION = '/dev/ttyUSB0'        # Serial connection
# MAVLINK_CONNECTION = 'udp:192.168.1.100:14550'  # Remote vehicle

# Output Configuration
SAVE_TO_FILE = True             # Save mission to waypoint file
OUTPUT_FILE = 'mission.waypoints'  # Output filename
UPLOAD_TO_VEHICLE = True        # Upload mission to connected vehicle
AUTO_START_MISSION = True       # Automatically arm and start mission after upload
VERBOSE_OUTPUT = False          # Enable verbose logging

# Mission End Behavior
MISSION_END_ACTION = 'RTL'      # What to do after mission: 'RTL' (Return to Launch), 'LAND' (Land in place), or 'NONE'

# ============================================================================


def get_drone_position(master: mavutil.mavlink_connection, timeout=10):
    """
    Retrieve drone's current GPS position using an existing MAVLink connection.
    
    Args:
        master: An active MAVLink connection object
        timeout: Timeout in seconds
        
    Returns:
        Point object with (lon, lat) or None if failed
    """
    if not master:
        print("  ✗ MAVLink connection is not valid for get_drone_position")
        return None

    try:
        print(f"\nRequesting drone position from system {master.target_system}...")
        
        # Request GPS position
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
            0, 0, 0, 0, 0, 0
        )
        
        # Wait for GLOBAL_POSITION_INT message
        msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=timeout)
        
        if msg:
            lat = msg.lat / 1e7
            lon = msg.lon / 1e7
            alt = msg.alt / 1000.0
            
            print(f"  ✓ Drone position: Lat={lat:.6f}, Lon={lon:.6f}, Alt={alt:.1f}m")
            return Point(lon, lat)
        else:
            print("  ✗ Timeout waiting for GPS position")
            return None
            
    except Exception as e:
        print(f"  ✗ Error getting drone position: {e}")
        return None


class PathToMavlink:
    """Converts optimized surveillance paths to MAVLink mission commands."""
    
    def __init__(self, waypoints, altitude=50, speed=5.0):
        """
        Initialize the MAVLink path converter.
        
        Args:
            waypoints: List of (lon, lat) tuples representing the path
            altitude: Flight altitude in meters (default: 50m)
            speed: Flight speed in m/s (default: 5.0 m/s)
        """
        self.waypoints = waypoints
        self.altitude = altitude
        self.speed = speed
        self.mission_items = []
        
    def create_mission_items(self, debug=False, include_takeoff=False):
        """
        Convert waypoints to MAVLink mission items.
        
        Args:
            debug: Print debug information
            include_takeoff: If True, include TAKEOFF as first item (often buggy)
        
        Returns:
            List of MAVLink mission item tuples
        """
        self.mission_items = []
        seq = 0
        
        # Add command to set the mission speed
        speed_item = (
            seq,                                    # Sequence number
            mavutil.mavlink.MAV_FRAME_MISSION,      # Frame
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, # Command
            1,                                      # Current (make this the first active command)
            1,                                      # Autocontinue
            1,                                      # Param1: Speed type (1=Airspeed)
            self.speed,                             # Param2: Speed (m/s)
            -1,                                     # Param3: Throttle (-1 for no change)
            0,                                      # Param4: Relative (0 for absolute speed)
            0,                                      # Param5: Latitude (unused)
            0,                                      # Param6: Longitude (unused)
            0,                                      # Param7: Altitude (unused)
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        )
        self.mission_items.append(speed_item)
        seq += 1

        # Optionally add TAKEOFF command (but it's buggy, so we'll handle takeoff manually)
        if include_takeoff and self.waypoints:
            first_lat = self.waypoints[0][1]
            first_lon = self.waypoints[0][0]
            
            takeoff_item = (
                seq,                                    # Sequence number
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # Frame
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,   # Command - TAKEOFF
                1,                                      # Current (1 for first item)
                1,                                      # Autocontinue
                0,                                      # Param1: Pitch
                0,                                      # Param2: Empty
                0,                                      # Param3: Empty
                0,                                      # Param4: Yaw angle (was nan, changed to 0)
                first_lat,                              # Param5: Latitude
                first_lon,                              # Param6: Longitude
                self.altitude,                          # Param7: Altitude
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION  # Mission type
            )
            
            if debug:
                print(f"\nDEBUG: Creating TAKEOFF command:")
                print(f"  Command ID: {mavutil.mavlink.MAV_CMD_NAV_TAKEOFF} (should be 22)")
                print(f"  Sequence: {seq}")
                print(f"  Frame: {mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT}")
                print(f"  Lat/Lon: {first_lat:.6f}, {first_lon:.6f}")
                print(f"  Altitude: {self.altitude}m")
            
            self.mission_items.append(takeoff_item)
            seq += 1
        
        # Add all waypoints (first one will be marked as current if no takeoff)
        for i, (lon, lat) in enumerate(self.waypoints):
            mission_item = (
                seq,                                    # Sequence number
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # Frame
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,  # Command
                0,                                     # Current (no longer the first item)
                1,                                      # Autocontinue
                0,                                      # Param1: Hold time (seconds)
                0,                                      # Param2: Acceptance radius (meters)
                0,                                      # Param3: Pass through waypoint
                0,                                      # Param4: Yaw angle (changed from nan to 0)
                lat,                                    # Param5: Latitude
                lon,                                    # Param6: Longitude
                self.altitude,                          # Param7: Altitude
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION  # Mission type
            )
            self.mission_items.append(mission_item)
            seq += 1
            
        return self.mission_items
    
    def add_mission_end_command(self, end_action='RTL'):
        """
        Add a final command to the mission (RTL or LAND).
        
        Args:
            end_action: 'RTL' to return to launch, 'LAND' to land in place, or 'NONE' for no action
        """
        if not self.mission_items or end_action == 'NONE':
            return
        
        seq = len(self.mission_items)
        
        if end_action == 'RTL':
            # Return to Launch command
            rtl_item = (
                seq,                                    # Sequence number
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # Frame
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,  # Command - RTL
                0,                                      # Current
                1,                                      # Autocontinue
                0, 0, 0, 0,                            # Params 1-4 (unused)
                0, 0, 0,                               # Lat, Lon, Alt (unused for RTL)
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION  # Mission type
            )
            self.mission_items.append(rtl_item)
            
        elif end_action == 'LAND':
            # Land in place command
            # Use last waypoint coordinates
            last_waypoint = self.waypoints[-1]
            last_lat = last_waypoint[1]
            last_lon = last_waypoint[0]
            
            land_item = (
                seq,                                    # Sequence number
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # Frame
                mavutil.mavlink.MAV_CMD_NAV_LAND,      # Command - LAND
                0,                                      # Current
                1,                                      # Autocontinue
                0,                                      # Param1: Abort alt (0 = use default)
                0,                                      # Param2: Land mode
                0,                                      # Param3: Empty
                0,                                      # Param4: Yaw angle
                last_lat,                               # Param5: Latitude
                last_lon,                               # Param6: Longitude
                0,                                      # Param7: Altitude (0 for landing)
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION  # Mission type
            )
            self.mission_items.append(land_item)
    
    def save_to_waypoint_file(self, filename):
        """
        Save mission items to a QGroundControl-compatible waypoint file.
        
        Args:
            filename: Output filename (e.g., 'mission.waypoints')
        """
        with open(filename, 'w') as f:
            f.write('QGC WPL 110\n')
            for item in self.mission_items:
                seq, frame, cmd, current, auto, p1, p2, p3, p4, lat, lon, alt, mission_type = item
                # Format: seq current frame command param1-4 lat lon alt autocontinue
                f.write(f'{seq}\t{current}\t{frame}\t{cmd}\t{p1}\t{p2}\t{p3}\t{p4}\t{lat}\t{lon}\t{alt}\t{auto}\n')
        
        print(f"Mission saved to {filename}")
    
    def upload_to_vehicle(self, master: mavutil.mavlink_connection, auto_start=False):
        """
        Upload mission to a connected vehicle using an existing connection.
        
        Args:
            master: An active MAVLink connection object
            auto_start: If True, arm and start mission automatically
            
        Returns:
            Tuple (success, master) - master is returned unmodified
        """
        if not master:
            print("  ✗ MAVLink connection is not valid for upload")
            return False, master

        print(f"\nUploading mission to vehicle on system {master.target_system}...")
        
        # Clear existing mission
        print("Clearing existing mission...")
        master.mav.mission_clear_all_send(master.target_system, master.target_component)
        master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
        
        # Send mission count
        print(f"Sending mission count: {len(self.mission_items)} waypoints")
        master.mav.mission_count_send(
            master.target_system,
            master.target_component,
            len(self.mission_items),
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        )
        
        # Upload each mission item
        for i, item in enumerate(self.mission_items):
            # Wait for mission request (can be MISSION_REQUEST or MISSION_REQUEST_INT)
            msg = master.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
            if not msg:
                print(f"Timeout waiting for mission request {i}")
                master.close()
                return False, master
            
            seq, frame, cmd, current, auto, p1, p2, p3, p4, lat, lon, alt, mission_type = item
            
            cmd_name = "TAKEOFF" if cmd == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF else "WAYPOINT"
            print(f"Sending waypoint {i+1}/{len(self.mission_items)} ({cmd_name}, cmd={cmd})")
            
            # Use MISSION_ITEM_INT (required by modern ArduPilot)
            # Convert lat/lon from degrees to int32 (degrees * 1e7)
            lat_int = int(lat * 1e7)
            lon_int = int(lon * 1e7)
            
            # Debug first item
            if i == 0:
                print(f"  DEBUG UPLOAD: seq={seq}, frame={frame}, cmd={cmd}, current={current}, auto={auto}")
                print(f"  DEBUG UPLOAD: p1={p1}, p2={p2}, p3={p3}, p4={p4}")
                print(f"  DEBUG UPLOAD: lat_int={lat_int}, lon_int={lon_int}, alt={alt}")
            
            # Manually create MISSION_ITEM_INT message to ensure correct field order
            # This avoids potential pymavlink parameter order issues
            msg = master.mav.mission_item_int_encode(
                master.target_system,     # target_system
                master.target_component,  # target_component
                seq,                      # seq
                frame,                    # frame
                cmd,                      # command - THIS IS THE CRITICAL FIELD
                current,                  # current
                auto,                     # autocontinue
                p1,                       # param1
                p2,                       # param2
                p3,                       # param3
                p4,                       # param4
                lat_int,                  # x (latitude as int32)
                lon_int,                  # y (longitude as int32)
                alt,                      # z (altitude)
                mission_type              # mission_type
            )
            master.mav.send(msg)
        
        # Wait for mission acknowledgment
        ack = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
        if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            print("Mission uploaded successfully!")
            
            # Verify the mission by reading it back
            print("\nVerifying mission on vehicle...")
            self.verify_mission(master)
            
            if auto_start:
                return self.arm_and_start_mission(master)
            else:
                return True, master
        else:
            print("Mission upload failed!")
            return False, master
    
    def verify_mission(self, master):
        """
        Read back and verify the mission from the vehicle.
        
        Args:
            master: MAVLink connection object
        """
        # Request mission count
        master.mav.mission_request_list_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION
        )
        
        # Get mission count
        msg = master.recv_match(type='MISSION_COUNT', blocking=True, timeout=5)
        if msg:
            print(f"  Vehicle has {msg.count} mission items")
            
            # Request first few items to verify TAKEOFF is there
            if msg.count > 0:
                master.mav.mission_request_int_send(
                    master.target_system,
                    master.target_component,
                    0,  # Request first item (seq 0)
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION
                )
                
                item = master.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=5)
                if item:
                    cmd_name = "TAKEOFF" if item.command == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF else "WAYPOINT" if item.command == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT else f"CMD_{item.command}"
                    print(f"  First item: {cmd_name} at seq {item.seq}")
                    if item.command != mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
                        print(f"  ⚠ WARNING: First item is not TAKEOFF! It's {cmd_name} (cmd={item.command})")
                else:
                    print("  ⚠ Could not read back first mission item")
        else:
            print("  ⚠ Could not read mission count from vehicle")
    
    def arm_and_start_mission(self, master):
        """
        Arm the vehicle and start the mission.
        Sets mode to GUIDED, arms, takes off manually, then switches to AUTO.
        
        Args:
            master: MAVLink connection object
            
        Returns:
            Tuple (success, master)
        """
        import time
        print("\n" + "="*60)
        print("         STARTING MISSION")
        print("="*60)
        
        # Step 1: Set mode to GUIDED
        print("\n1. Setting flight mode to GUIDED...")
        mode_id = master.mode_mapping().get('GUIDED')
        if mode_id is None:
            print("  ✗ GUIDED mode not available")
            return False, master
        
        master.mav.set_mode_send(
            master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )
        time.sleep(1)
        print("  ✓ Mode set to GUIDED")
        
        # Step 2: Arm the vehicle
        print("\n2. Arming vehicle...")
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
        if msg:
            is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            if not is_armed:
                master.mav.command_long_send(
                    master.target_system,
                    master.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0,
                    1, 0, 0, 0, 0, 0, 0
                )
                
                ack = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
                if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    print("  ✓ Vehicle armed successfully")
                    time.sleep(2)
                else:
                    print("  ✗ Failed to arm vehicle")
                    return False, master
            else:
                print("  Vehicle already armed")
        
        # Step 3: Command takeoff in GUIDED mode
        print(f"\n3. Taking off to {self.altitude}m in GUIDED mode...")
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0,  # param1: pitch
            0,  # param2: empty
            0,  # param3: empty
            0,  # param4: yaw
            0,  # param5: latitude (0 = current position)
            0,  # param6: longitude (0 = current position)
            self.altitude  # param7: altitude
        )
        
        ack = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            print("  ✓ Takeoff command accepted")
        else:
            print("  ⚠ Takeoff command may have failed, but continuing...")
        
        # Wait for takeoff to complete
        print("  Waiting for takeoff to complete...")
        time.sleep(8)  # Give it time to climb
        
        # Step 4: Switch to AUTO mode to execute the mission
        print("\n4. Setting flight mode to AUTO to start mission...")
        mode_id = master.mode_mapping().get('AUTO')
        if mode_id is None:
            print("  ✗ AUTO mode not available")
            return False, master
        
        master.mav.set_mode_send(
            master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )
        time.sleep(1)
        print("  ✓ Mode set to AUTO")
        
        print("\n✓ Mission started! The drone should now follow the waypoints.")
        print("="*60 + "\n")
        
        return True, master
    
    def print_mission_summary(self):
        """Print a summary of the mission."""
        print("\n" + "="*60)
        print("             MAVLINK MISSION SUMMARY")
        print("="*60)
        print(f"  Total Mission Items: {len(self.mission_items)}")
        print(f"  Survey Waypoints:    {len(self.waypoints)}")
        print(f"  Flight Altitude:     {self.altitude} meters")
        print(f"  Flight Speed:        {self.speed} m/s")
        print("="*60)
        print("\nMission Item List:")
        for i, item in enumerate(self.mission_items):
            seq, frame, cmd, current, auto, p1, p2, p3, p4, lat, lon, alt, mission_type = item
            
            # Map command ID to readable name
            cmd_names = {
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF: "TAKEOFF",
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT: "WAYPOINT",
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH: "RTL",
                mavutil.mavlink.MAV_CMD_NAV_LAND: "LAND"
            }
            cmd_name = cmd_names.get(cmd, f"CMD_{cmd}")
            
            print(f"  {i+1:3d}. {cmd_name:8s}: Lat={lat:11.6f}, Lon={lon:11.6f}, Alt={alt:6.1f}m")
        print("="*60 + "\n")
    
    def plot_mission_path(self, geofence_coords=None, show=True):
        """
        Visualize the surveillance path before mission execution.
        
        Args:
            geofence_coords: List of (lon, lat) tuples for geofence boundary
            show: If True, display the plot immediately
        """
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # Plot geofence if provided
        if geofence_coords:
            geofence_polygon = ShapelyPolygon(geofence_coords)
            gx, gy = geofence_polygon.exterior.xy
            ax.plot(gx, gy, label='Geofence', color='blue', linewidth=2.5, zorder=3)
            ax.fill(gx, gy, alpha=0.1, fc='blue', ec='none', zorder=1)
        
        # Calculate coverage area
        if self.waypoints and len(self.waypoints) > 1:
            meters_per_degree_lat = 111320.0
            sensor_buffer_deg = (30 / 2.0) / meters_per_degree_lat  # Approximate sensor width
            
            path_line = LineString([(wp[0], wp[1]) for wp in self.waypoints])
            coverage_area = path_line.buffer(sensor_buffer_deg, cap_style=3)
            
            # Plot coverage area
            if coverage_area.geom_type == 'Polygon':
                cx, cy = coverage_area.exterior.xy
                ax.fill(cx, cy, alpha=0.25, fc='lightgreen', ec='none', label='Coverage Area', zorder=2)
            elif coverage_area.geom_type == 'MultiPolygon':
                for i, poly in enumerate(coverage_area.geoms):
                    cx, cy = poly.exterior.xy
                    ax.fill(cx, cy, alpha=0.25, fc='lightgreen', ec='none', 
                           label='Coverage Area' if i == 0 else "", zorder=2)
        
        # Plot waypoints
        if self.waypoints:
            lons = [wp[0] for wp in self.waypoints]
            lats = [wp[1] for wp in self.waypoints]
            
            # Draw path lines
            ax.plot(lons, lats, color='red', linewidth=2, linestyle='-', 
                   label='Flight Path', zorder=4, alpha=0.7)
            
            # Draw waypoint markers
            ax.scatter(lons, lats, color='red', s=50, zorder=5, 
                      edgecolors='darkred', linewidth=1, label='Waypoints')
            
            # Mark start point
            ax.scatter(lons[0], lats[0], color='green', s=200, marker='*', 
                      zorder=6, edgecolors='darkgreen', linewidth=2, label='Start Point')
            
            # Mark end point
            ax.scatter(lons[-1], lats[-1], color='orange', s=150, marker='s', 
                      zorder=6, edgecolors='darkorange', linewidth=2, label='End Point')
            
            # Add waypoint numbers for first, last, and every 5th waypoint
            for i, (lon, lat) in enumerate(self.waypoints):
                if i == 0 or i == len(self.waypoints) - 1 or i % 5 == 0:
                    ax.annotate(f'{i+1}', (lon, lat), xytext=(5, 5), 
                               textcoords='offset points', fontsize=8, 
                               fontweight='bold', color='darkred',
                               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
        
        # Styling
        ax.set_title('Surveillance Mission Path Preview', fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('Longitude', fontsize=11)
        ax.set_ylabel('Latitude', fontsize=11)
        ax.legend(loc='best', fontsize=9, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.axis('equal')
        
        # Add mission info text box
        if self.waypoints:
            info_text = f"Waypoints: {len(self.waypoints)}\n"
            info_text += f"Altitude: {self.altitude}m\n"
            info_text += f"Speed: {self.speed} m/s"
            
            if geofence_coords:
                path_line = LineString([(wp[0], wp[1]) for wp in self.waypoints])
                path_length_deg = path_line.length
                path_length_km = path_length_deg * 111.320
                flight_time_min = (path_length_km * 1000 / self.speed) / 60
                info_text += f"\nDistance: {path_length_km:.2f} km"
                info_text += f"\nEst. Time: {flight_time_min:.1f} min"
            
            ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        if show:
            plt.show()
        
        return fig, ax


def generate_optimized_path(kml_file, uav_start_location, sensor_width, overlap, 
                           altitude=50, speed=5.0, verbose=False):
    """
    Generate an optimized surveillance path from a KML geofence.
    
    Args:
        kml_file: Path to KML file containing geofence
        uav_start_location: Point object with UAV starting position
        sensor_width: Sensor footprint width in meters
        overlap: Overlap percentage (e.g., 0.2 for 20%)
        altitude: Flight altitude in meters
        speed: Flight speed in m/s
        verbose: Enable verbose output
    
    Returns:
        Tuple (PathToMavlink object, geofence_coords) with mission ready to upload
    """
    print("\n" + "="*60)
    print("         SURVEILLANCE PATH GENERATION")
    print("="*60)
    
    # Parse KML file
    try:
        print(f"Parsing KML file: {kml_file}")
        geofence_coords = load_kml_boundary(kml_file)
        geofence = Polygon(geofence_coords)
        print(f"  ✓ Successfully parsed geofence with {len(geofence_coords)} vertices")
    except Exception as e:
        print(f"  ✗ Error parsing KML: {e}")
        sys.exit(1)
    
    # Find best entry point
    print("\nOptimizing entry point...")
    entry_point, optimal_path, metrics, candidates, candidate_paths, best_candidate = choose_best_entry_point(
        geofence, uav_start_location, overlap, sensor_width
    )
    
    if verbose:
        print("  Entry point candidates:")
        for m in metrics:
            axis = "Short" if m['short_axis'] else "Long"
            print(f"    Corner {m['corner_index']}, {axis} axis: " +
                  f"coverage={m['coverage_ratio']:.1%}, " +
                  f"waypoints={m['waypoints']}")
    
    best_axis = "Short" if best_candidate['short_axis'] else "Long"
    print(f"  ✓ Selected entry: Lat={entry_point.y:.6f}, Lon={entry_point.x:.6f} ({best_axis} axis)")
    
    # Optimize overlap
    print("\nOptimizing overlap percentage...")
    best_overlap, best_overlap_path, overlap_metrics, overlaps, overlap_paths, \
        best_overlap_idx, best_overlap_short_axis = choose_best_overlap(
        geofence, entry_point, overlap, sensor_width
    )
    
    print(f"  ✓ Selected overlap: {best_overlap:.1%}")
    
    if best_overlap_path and len(best_overlap_path) > 1:
        optimal_path = best_overlap_path
    
    # Path optimization pipeline
    print("\nApplying path optimizations...")
    initial_waypoints = len(optimal_path)
    
    # Coverage barrier pruning
    optimal_path = prune_path_by_coverage_barrier(
        optimal_path, geofence, sensor_width,
        coverage_barrier_ratio=0.95,
        min_marginal_gain_ratio_per_deg=0.005,
        consecutive_steps=2,
        debug=False
    )
    if len(optimal_path) < initial_waypoints:
        print(f"  ✓ Coverage barrier pruning: {initial_waypoints} → {len(optimal_path)} waypoints")
        initial_waypoints = len(optimal_path)
    
    # Return leg pruning
    optimal_path = prune_return_with_low_gain(
        optimal_path, entry_point, geofence, sensor_width,
        coverage_barrier_ratio=0.95,
        min_marginal_gain_ratio_per_deg=0.005,
        consecutive_steps=2,
        min_return_delta_deg=0.0003
    )
    if len(optimal_path) < initial_waypoints:
        print(f"  ✓ Return leg pruning: {initial_waypoints} → {len(optimal_path)} waypoints")
        initial_waypoints = len(optimal_path)
    
    # Waypoint shortcutting
    optimal_path = shortcut_redundant_waypoints(
        optimal_path, geofence, sensor_width,
        coverage_loss_threshold=0.003,
        debug=False
    )
    if len(optimal_path) < initial_waypoints:
        print(f"  ✓ Waypoint shortcutting: {initial_waypoints} → {len(optimal_path)} waypoints")
        initial_waypoints = len(optimal_path)
    
    # Final tail trimming
    optimal_path = trim_redundant_tail(
        optimal_path, geofence, sensor_width,
        relative_gain_threshold=0.005,
        debug=False
    )
    if len(optimal_path) < initial_waypoints:
        print(f"  ✓ Tail trimming: {initial_waypoints} → {len(optimal_path)} waypoints")
    
    # Prepend the UAV's actual starting location to the mission
    if optimal_path:
        uav_start_coords = (uav_start_location.x, uav_start_location.y)
        # Check if start is not already the first waypoint to avoid duplicates
        if Point(optimal_path[0]).distance(uav_start_location) > 1e-6:
             optimal_path.insert(0, uav_start_coords)
             print(f"  ✓ Prepended UAV start location. New total: {len(optimal_path)} waypoints")
    
    # Calculate final metrics
    final_coverage, final_length_deg = compute_path_metrics(geofence, optimal_path, sensor_width)
    final_length_km = final_length_deg * 111.320  # Convert to km
    
    print("\n" + "="*60)
    print("             PATH GENERATION COMPLETE")
    print("="*60)
    print(f"  Waypoints:    {len(optimal_path)}")
    print(f"  Coverage:     {final_coverage:.1%}")
    print(f"  Path Length:  {final_length_km:.2f} km")
    print(f"  Flight Time:  {(final_length_km * 1000 / speed / 60):.1f} minutes @ {speed} m/s")
    print("="*60 + "\n")
    
    # Convert to MAVLink mission
    # Note: We don't include TAKEOFF in mission due to MAVLink protocol issues
    # Instead, we handle takeoff manually in GUIDED mode
    mavlink_mission = PathToMavlink(optimal_path, altitude=altitude, speed=speed)
    mavlink_mission.create_mission_items(debug=False, include_takeoff=False)
    
    # Add mission end command (RTL or LAND)
    mavlink_mission.add_mission_end_command(end_action=MISSION_END_ACTION)
    
    return mavlink_mission, geofence_coords


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Generate optimized surveillance paths and convert to MAVLink missions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default parameters from configuration section (edit the file)
  python path_creation_mavlink.py
  
  # Override with command-line arguments
  python path_creation_mavlink.py --kml geofence.kml --output mission.waypoints
  
  # Upload mission to SITL
  python path_creation_mavlink.py --kml geofence.kml --upload udp:127.0.0.1:14550
  
  # Custom parameters
  python path_creation_mavlink.py --kml geofence.kml --altitude 100 --speed 10 --sensor-width 40
        """
    )
    
    # All arguments are now optional - defaults come from configuration section
    parser.add_argument('--kml', help=f'Path to KML geofence file (default: {KML_FILE})')
    parser.add_argument('--output', '-o', help=f'Output waypoint file (default: {OUTPUT_FILE if SAVE_TO_FILE else "None"})')
    parser.add_argument('--upload', '-u', help=f'Upload mission to vehicle (default: {MAVLINK_CONNECTION if UPLOAD_TO_VEHICLE else "None"})')
    parser.add_argument('--start-lat', type=float, help=f'UAV starting latitude (default: from drone if USE_DRONE_POSITION=True, else {UAV_START_LAT})')
    parser.add_argument('--start-lon', type=float, help=f'UAV starting longitude (default: from drone if USE_DRONE_POSITION=True, else {UAV_START_LON})')
    parser.add_argument('--use-drone-position', action='store_true', help='Fetch starting position from connected drone')
    parser.add_argument('--use-manual-position', action='store_true', help='Use manual lat/lon instead of drone position')
    parser.add_argument('--altitude', '-a', type=float, help=f'Flight altitude in meters (default: {FLIGHT_ALTITUDE})')
    parser.add_argument('--speed', '-s', type=float, help=f'Flight speed in m/s (default: {FLIGHT_SPEED})')
    parser.add_argument('--sensor-width', '-w', type=float, help=f'Sensor footprint width in meters (default: {SENSOR_WIDTH})')
    parser.add_argument('--overlap', type=float, help=f'Overlap percentage 0-1 (default: {OVERLAP})')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--no-save', action='store_true', help='Disable saving to file')
    parser.add_argument('--no-upload', action='store_true', help='Disable uploading to vehicle')
    parser.add_argument('--auto-start', action='store_true', help='Automatically arm and start mission after upload')
    parser.add_argument('--no-auto-start', action='store_true', help='Do not automatically start mission')
    parser.add_argument('--end-action', choices=['RTL', 'LAND', 'NONE'], help=f'Mission end action (default: {MISSION_END_ACTION})')
    
    args = parser.parse_args()
    
    # Use configuration defaults, override with command-line arguments if provided
    kml_file = args.kml if args.kml else KML_FILE
    altitude = args.altitude if args.altitude is not None else FLIGHT_ALTITUDE
    speed = args.speed if args.speed is not None else FLIGHT_SPEED
    sensor_width = args.sensor_width if args.sensor_width is not None else SENSOR_WIDTH
    overlap = args.overlap if args.overlap is not None else OVERLAP
    verbose = args.verbose if args.verbose else VERBOSE_OUTPUT
    
    # Output configuration
    save_to_file = not args.no_save and (args.output or SAVE_TO_FILE)
    output_file = args.output if args.output else OUTPUT_FILE
    upload_to_vehicle = not args.no_upload and (args.upload or UPLOAD_TO_VEHICLE)
    connection_string = args.upload if args.upload else MAVLINK_CONNECTION
    
    # Auto-start configuration
    auto_start = AUTO_START_MISSION
    if args.auto_start:
        auto_start = True
    if args.no_auto_start:
        auto_start = False
    
    # Determine whether to use drone position or manual position
    use_drone_pos = USE_DRONE_POSITION
    if args.use_drone_position:
        use_drone_pos = True
    if args.use_manual_position:
        use_drone_pos = False
    
    # Get starting position
    uav_start = None
    start_lat = None
    start_lon = None
    
    # If manual coordinates provided via command line, use those
    if args.start_lat is not None and args.start_lon is not None:
        start_lat = args.start_lat
        start_lon = args.start_lon
        uav_start = Point(start_lon, start_lat)
        use_drone_pos = False
        print("\nUsing manual coordinates from command-line arguments")
    
    # Otherwise, fetch from drone if enabled
    elif use_drone_pos:
        # For standalone script, create a temporary connection
        print(f"\nConnecting to {connection_string} to get current position...")
        temp_master = mavutil.mavlink_connection(connection_string)
        temp_master.wait_heartbeat()
        uav_start = get_drone_position(temp_master)
        temp_master.close()
        
        if uav_start:
            start_lon = uav_start.x
            start_lat = uav_start.y
        else:
            print("\n⚠ Warning: Could not fetch drone position, using manual coordinates")
            start_lat = UAV_START_LAT
            start_lon = UAV_START_LON
            uav_start = Point(start_lon, start_lat)
    
    # Use manual coordinates from config
    else:
        start_lat = UAV_START_LAT
        start_lon = UAV_START_LON
        uav_start = Point(start_lon, start_lat)
        print("\nUsing manual coordinates from configuration")
    
    # Validate parameters
    if overlap < 0 or overlap > 1:
        print("Error: Overlap must be between 0 and 1")
        sys.exit(1)
    
    if altitude <= 0:
        print("Error: Altitude must be positive")
        sys.exit(1)
    
    if speed <= 0:
        print("Error: Speed must be positive")
        sys.exit(1)
    
    if not save_to_file and not upload_to_vehicle:
        print("Warning: Neither save nor upload is enabled. Enable at least one option.")
        print("  Set SAVE_TO_FILE = True or UPLOAD_TO_VEHICLE = True in configuration,")
        print("  or use --output or --upload command-line arguments.")
        sys.exit(1)
    
    if not uav_start:
        print("Error: Could not determine UAV starting position")
        sys.exit(1)
    
    print("\nUsing Configuration:")
    print(f"  KML File:     {kml_file}")
    print(f"  Start Point:  Lat={start_lat}, Lon={start_lon}")
    print(f"  Altitude:     {altitude} m")
    print(f"  Speed:        {speed} m/s")
    print(f"  Sensor Width: {sensor_width} m")
    print(f"  Overlap:      {overlap*100:.0f}%")
    if save_to_file:
        print(f"  Output File:  {output_file}")
    if upload_to_vehicle:
        print(f"  Connection:   {connection_string}")
    print()
    
    # Generate optimized path and convert to MAVLink
    mavlink_mission, geofence_coords = generate_optimized_path(
        kml_file=kml_file,
        uav_start_location=uav_start,
        sensor_width=sensor_width,
        overlap=overlap,
        altitude=altitude,
        speed=speed,
        verbose=verbose
    )
    
    # Print mission summary
    mavlink_mission.print_mission_summary()
    
    # Visualize the mission path
    print("📊 Displaying surveillance path visualization...")
    print("   Close the plot window to continue with mission upload.\n")
    mavlink_mission.plot_mission_path(geofence_coords=geofence_coords, show=True)
    
    # Save to file if requested
    if save_to_file:
        mavlink_mission.save_to_waypoint_file(output_file)
    
    # Upload to vehicle if requested
    if upload_to_vehicle:
        # For standalone script, create the main connection here
        print(f"Connecting to vehicle on {connection_string} for mission upload...")
        master = mavutil.mavlink_connection(connection_string)
        master.wait_heartbeat()
        
        success, _ = mavlink_mission.upload_to_vehicle(master, auto_start=auto_start)
        
        if success:
            print("✓ Mission successfully uploaded to vehicle")
            if not auto_start:
                print("\nTo start the mission manually:")
                print("  1. Arm the vehicle (if not already armed)")
                print("  2. Set mode to AUTO")
                print("  Or run with --auto-start flag to do this automatically")
            if master:
                master.close()
        else:
            print("✗ Mission upload failed")
            if master:
                master.close()
            sys.exit(1)
    
    print("\n✓ All operations completed successfully")


if __name__ == '__main__':
    main()

