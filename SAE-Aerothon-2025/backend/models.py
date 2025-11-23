from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


# --- Core Telemetry Models ---

@dataclass
class AHRS:
    omegaIx: float
    omegaIy: float
    omegaIz: float
    accel_weight: float
    renorm_val: float
    error_rp: float
    error_yaw: float


@dataclass
class AHRS2:
    roll: float
    pitch: float
    yaw: float
    altitude: float
    lat: int
    lng: int


@dataclass
class RAW_IMU:
    time_usec: int
    xacc: int
    yacc: int
    zacc: int
    xgyro: int
    ygyro: int
    zgyro: int
    xmag: int
    ymag: int
    zmag: int
    id: int
    temperature: int


@dataclass
class RC_CHANNELS:
    time_boot_ms: int
    chancount: int
    chan1_raw: int
    chan2_raw: int
    chan3_raw: int
    chan4_raw: int
    rssi: int


@dataclass
class SYS_STATUS:
    onboard_control_sensors_present: int
    onboard_control_sensors_enabled: int
    onboard_control_sensors_health: int
    load: int
    voltage_battery: int
    current_battery: int
    battery_remaining: int
    drop_rate_comm: int
    errors_comm: int


@dataclass
class POWER_STATUS:
    Vcc: int
    Vservo: int
    flags: int


@dataclass
class MEMINFO:
    brkval: int
    freemem: int
    freemem32: int


@dataclass
class VIBRATION:
    time_usec: int
    vibration_x: float
    vibration_y: float
    vibration_z: float
    clipping_0: int
    clipping_1: int
    clipping_2: int


@dataclass
class EKF_STATUS_REPORT:
    flags: int
    velocity_variance: float
    pos_horiz_variance: float
    pos_vert_variance: float
    compass_variance: float
    terrain_alt_variance: float
    airspeed_variance: float


# --- Universal Packet Wrapper ---
@dataclass
class TelemetryPacket:
    type: str
    data: Dict[str, Any]

    def to_json(self):
        return {
            "type": self.type,
            "data": self.data
        }

    @staticmethod
    def from_msg(msg):
        """
        Converts a pymavlink message into a TelemetryPacket model.
        """
        msg_dict = msg.to_dict()
        return TelemetryPacket(type=msg.get_type(), data=msg_dict)
