# Raspberry Pi Companion Computer

Complete companion computer software for running on a Raspberry Pi aboard a drone. Handles camera streaming, MAVLink telemetry relay, and command forwarding between the Pixhawk flight controller and Ground Control Station (GCS).

## Features

- **Camera Streaming**: Streams video from RPi camera or USB webcam to GCS via UDP
- **MAVLink Relay**: Bidirectional MAVLink communication between Pixhawk and GCS
- **System Monitoring**: Monitors CPU, memory, temperature, and network statistics
- **Low Latency**: Optimized for minimal delay in video and telemetry
- **Auto-Start**: Systemd service for automatic startup on boot
- **Configurable**: Easy YAML configuration file

## Hardware Requirements

- Raspberry Pi 3/4/5 (or compatible)
- Pixhawk flight controller connected via USB or UART
- RPi Camera Module or USB webcam
- WiFi connection to GCS

## Installation

### 1. Copy Files to Raspberry Pi

```bash
# On your computer, copy the rpi_companion folder to the RPi
scp -r rpi_companion pi@raspberrypi.local:/home/pi/
```

### 2. SSH into Raspberry Pi

```bash
ssh pi@raspberrypi.local
cd /home/pi/rpi_companion
```

### 3. Run Installation Script

```bash
chmod +x install.sh
./install.sh
```

This will:
- Install system dependencies
- Install Python packages
- Create log directory
- Add user to dialout group (for serial access)
- Install systemd service

### 4. Configure

Edit `config.yaml` with your settings:

```bash
nano config.yaml
```

**Important settings to change:**
- `gcs.ip`: IP address of your GCS computer
- `pixhawk.serial_port`: Serial port of your Pixhawk (usually `/dev/ttyACM0`)
- `camera.device`: Camera device (0 for RPi camera, `/dev/video0` for USB)

## Usage

### Manual Start (for testing)

```bash
./start_companion.sh
```

Press `Ctrl+C` to stop.

### Auto-Start on Boot

```bash
# Enable service
sudo systemctl enable companion

# Start service
sudo systemctl start companion

# Check status
sudo systemctl status companion

# View logs
journalctl -u companion -f
```

### Stop Service

```bash
sudo systemctl stop companion
```

## Configuration

### config.yaml

```yaml
gcs:
  ip: "192.168.1.100"      # GCS IP address
  video_port: 5600          # Video streaming port
  telemetry_port: 14550     # Telemetry port
  command_port: 14551       # Command port

pixhawk:
  serial_port: "/dev/ttyACM0"  # Pixhawk serial port
  baud_rate: 57600              # Baud rate

camera:
  device: 0                # Camera device
  width: 640               # Resolution width
  height: 480              # Resolution height
  fps: 30                  # Frame rate
  quality: 80              # JPEG quality (1-100)
```

## Troubleshooting

### Camera Not Working

```bash
# List video devices
ls -l /dev/video*

# Test camera
raspistill -o test.jpg  # For RPi camera
```

### Pixhawk Not Connecting

```bash
# Check serial ports
ls -l /dev/ttyACM* /dev/ttyUSB*

# Check permissions
groups  # Should include 'dialout'

# If not, add user and reboot
sudo usermod -a -G dialout $USER
sudo reboot
```

### No Video on GCS

1. Check GCS IP in `config.yaml`
2. Verify network connectivity: `ping <GCS_IP>`
3. Check firewall on GCS allows UDP port 5600
4. View logs: `journalctl -u companion -f`

### High CPU Usage

- Reduce camera resolution in `config.yaml`
- Lower FPS (e.g., 15-20)
- Reduce JPEG quality (e.g., 60-70)

## Network Setup

### WiFi Hotspot Mode (Recommended)

Configure RPi as WiFi hotspot so GCS can connect directly:

```bash
sudo apt-get install hostapd dnsmasq
# Configure as access point (see online guides)
```

### Station Mode

Connect RPi to existing WiFi network and note its IP address.

## File Structure

```
rpi_companion/
├── main.py                 # Main orchestrator
├── camera_streamer.py      # Camera streaming module
├── mavlink_relay.py        # MAVLink relay module
├── system_monitor.py       # System monitoring
├── config.yaml             # Configuration
├── requirements.txt        # Python dependencies
├── install.sh              # Installation script
├── start_companion.sh      # Startup script
├── systemd/
│   └── companion.service   # Systemd service
└── README.md              # This file
```

## Performance Tips

1. **Reduce Latency**:
   - Use wired connection if possible
   - Reduce camera resolution (640x480 is good balance)
   - Use quality 70-80 for JPEG

2. **Improve Reliability**:
   - Use 5GHz WiFi if available
   - Keep RPi cool (add heatsink/fan)
   - Use quality power supply (5V 3A minimum)

3. **Bandwidth Usage**:
   - 640x480 @ 30fps, quality 80: ~2-3 Mbps
   - 1280x720 @ 30fps, quality 80: ~5-8 Mbps
   - Telemetry: ~10 Kbps

## Integration with GCS

On the GCS side, configure the backend to receive:
- Video stream on UDP port 5600
- Telemetry on UDP port 14550
- Send commands to UDP port 14551

Update GCS `video_stream.py` to use UDP source:
```python
video_manager = VideoManager(source="udp://0.0.0.0:5600")
```

## License

Part of SAE Aerothon GCS project.

## Support

For issues or questions, check the logs:
```bash
journalctl -u companion -f
```
