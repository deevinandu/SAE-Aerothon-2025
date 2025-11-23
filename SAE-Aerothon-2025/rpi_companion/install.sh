#!/bin/bash
# Raspberry Pi Companion Computer - Installation Script

set -e  # Exit on error

echo "========================================="
echo "RPi Companion Computer - Installation"
echo "========================================="

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNING: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-opencv \
    python3-yaml \
    python3-psutil \
    libatlas-base-dev \
    libopenjp2-7 \
    libtiff5

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Create log directory
echo "Creating log directory..."
sudo mkdir -p /var/log
sudo touch /var/log/companion.log
sudo chmod 666 /var/log/companion.log

# Add user to dialout group (for serial port access)
echo "Adding user to dialout group..."
sudo usermod -a -G dialout $USER

# Make scripts executable
echo "Making scripts executable..."
chmod +x main.py
chmod +x start_companion.sh
chmod +x install.sh

# Install systemd service
echo "Installing systemd service..."
sudo cp systemd/companion.service /etc/systemd/system/
sudo systemctl daemon-reload

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your GCS IP and settings"
echo "2. Test manually: ./start_companion.sh"
echo "3. Enable auto-start: sudo systemctl enable companion"
echo "4. Start service: sudo systemctl start companion"
echo "5. View logs: journalctl -u companion -f"
echo ""
echo "NOTE: You may need to log out and back in for group changes to take effect"
echo ""
