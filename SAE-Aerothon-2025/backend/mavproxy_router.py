import subprocess
import atexit
import sys
import logging
import time

# Configure logging
logger = logging.getLogger(__name__)

# Global variable to hold the MAVProxy process instance
mavproxy_process = None

def stop_mavproxy():
    """
    Terminates the MAVProxy subprocess if it is running.
    This function is registered with atexit to be called on script exit.
    """
    global mavproxy_process
    if mavproxy_process and mavproxy_process.poll() is None:
        logger.info("Terminating MAVProxy router process (PID: %d)...", mavproxy_process.pid)
        try:
            mavproxy_process.terminate()
            # Wait for a few seconds for graceful shutdown
            mavproxy_process.wait(timeout=5)
            logger.info("MAVProxy router process terminated.")
        except subprocess.TimeoutExpired:
            logger.warning("MAVProxy process did not terminate gracefully. Killing it.")
            mavproxy_process.kill()
            mavproxy_process.wait()
            logger.info("MAVProxy router process killed.")
        except Exception as e:
            logger.error(f"Error terminating MAVProxy: {e}")
        finally:
            mavproxy_process = None

def start_mavproxy(connection_string: str, baud_rate: int = 57600):
    """
    Launches MAVProxy as a background process to route MAVLink data.

    Args:
        connection_string (str): The serial port for the drone connection (e.g., /dev/ttyUSB0).
        baud_rate (int): The baud rate for the serial connection.

    Returns:
        A dictionary with telemetry and mission connection strings if successful, otherwise None.
    """
    global mavproxy_process

    if mavproxy_process and mavproxy_process.poll() is None:
        logger.warning("MAVProxy router is already running. Stopping it before restarting.")
        stop_mavproxy()

    # Hardcoded port configuration
    telemetry_out = "127.0.0.1:14660"
    mission_out = "127.0.0.1:14661"

    command = [
        sys.executable,
        "-m", "mavproxy",
        "--master", connection_string,
        "--baudrate", str(baud_rate),
        "--out", telemetry_out,
        "--out", mission_out,
    ]

    logger.info(f"Starting MAVProxy with command: {' '.join(command)}")

    try:
        # Launch MAVProxy as a non-blocking background process and suppress its output.
        mavproxy_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Give it a moment to start and check if it exited immediately
        time.sleep(2)
        if mavproxy_process.poll() is not None:
            logger.error(
                "MAVProxy process failed to start. It terminated with exit code %d. "
                "Ensure MAVProxy is installed ('pip install pymavlink') and the serial device is correct.",
                mavproxy_process.returncode
            )
            mavproxy_process = None
            return None

        logger.info(f"MAVProxy router process started successfully (PID: {mavproxy_process.pid}).")
        logger.info(f"  - Telemetry output (UDP): {telemetry_out}")
        logger.info(f"  - Mission output (UDP):   {mission_out}")

        # Register the cleanup function to be called on script exit
        atexit.register(stop_mavproxy)
        
        return {
            "telemetry_conn_str": f"udp:{telemetry_out}",
            "mission_conn_str": f"udp:{mission_out}",
        }

    except FileNotFoundError:
        logger.error("Could not launch MAVProxy. Please ensure 'pymavlink' is installed ('pip install pymavlink').")
        mavproxy_process = None
        return None
    except Exception as e:
        logger.error(f"An error occurred while launching MAVProxy: {e}")
        mavproxy_process = None
        return None
