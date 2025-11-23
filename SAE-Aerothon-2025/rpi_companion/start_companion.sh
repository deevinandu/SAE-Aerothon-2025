#!/bin/bash
# Raspberry Pi Companion Computer - Startup Script

echo "Starting RPi Companion Computer..."

# Get script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check if config exists
if [ ! -f "config.yaml" ]; then
    echo "ERROR: config.yaml not found!"
    echo "Please copy config.yaml.example to config.yaml and edit it"
    exit 1
fi

# Run main script
python3 main.py
