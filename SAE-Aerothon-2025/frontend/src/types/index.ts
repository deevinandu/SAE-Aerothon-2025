// Types for the GCS application
export interface VideoSource {
  type: "Webcam" | "UDP" | "TCP" | "RTSP" | "HTTP" | "File";
  connectionString: string;
  isActive: boolean;
}

export interface DetectedObject {
  object_id: string;
  label: string;
  confidence?: number;
  bbox?: [number, number, number, number]; // [x, y, width, height]
  is_new?: boolean;
  first_seen?: number;
  last_seen?: number;
  processed_image_size?: [number, number]; // [width, height] of processed image
}

export interface AnalysisResult {
  labels: string[];
  points: [number, number][]; // [x, y] coordinates
  bboxes: [number, number, number, number][]; // [x, y, width, height]
  objects: DetectedObject[];
  unique_objects_count?: number;
  session_summary?: string;
}

export interface SessionState {
  session_id: string;
  frame_number: number;
  is_recording: boolean;
  unique_objects: Record<string, DetectedObject>;
  start_time: Date;
  last_analysis: AnalysisResult | null;
  latency_ms: number | null;
}

export interface SystemStats {
  fps: number;
  frame_count: number;
  analysis_count: number;
  objects_detected: number;
  session_duration: number;
  memory_usage?: number;
}

export interface GCSConfig {
  backend_url: string;
  analysis_interval: number; // seconds
  auto_record: boolean;
  video_quality: number;
  enable_object_tracking: boolean;
}

// Telemetry Data Types - Based on MAVLink messages
export interface GPSData {
  latitude: number; // degrees
  longitude: number; // degrees
  altitude: number; // meters
  speed: number; // m/s
  heading: number; // degrees
  fix_type: number; // GPS fix type (0-6)
  satellites: number; // number of satellites
  timestamp: string;
}

export interface AttitudeData {
  roll: number; // radians
  pitch: number; // radians
  yaw: number; // radians
  rollspeed: number; // rad/s
  pitchspeed: number; // rad/s
  yawspeed: number; // rad/s
}

export interface VFRHUDData {
  airspeed: number; // m/s
  groundspeed: number; // m/s
  heading: number; // degrees
  throttle: number; // %
  alt: number; // meters
  climb: number; // m/s
}

export interface BatteryData {
  voltage: number; // V
  current: number; // A
  remaining: number; // %
}

export interface SystemStatus {
  load: number; // %
  voltage_battery: number; // V
  current_battery: number; // A
  battery_remaining: number; // %
  sensors_present: number; // bitmask
  sensors_enabled: number; // bitmask
  sensors_health: number; // bitmask
}

export interface DroneStatus {
  armed: boolean;
  mode: string;
}

export interface TelemetryData {
  gps: GPSData;
  attitude: AttitudeData;
  vfr_hud: VFRHUDData;
  battery: BatteryData;
  system: SystemStatus;
  status: DroneStatus;
  session_id?: string;
  timestamp: string;
}
