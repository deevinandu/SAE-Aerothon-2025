#!/usr/bin/env python3
"""
System Monitor Module

Monitors system health including CPU, memory, temperature, and network statistics.
Logs metrics periodically for debugging and performance analysis.
"""

import logging
import time
import psutil
import os

logger = logging.getLogger('system_monitor')

class SystemMonitor:
    """Monitors system health and performance"""
    
    def __init__(self, log_interval=30):
        self.log_interval = log_interval
        self.running = False
        
    def run(self):
        """Main monitoring loop"""
        logger.info(f"System monitor started (logging every {self.log_interval}s)")
        self.running = True
        
        while self.running:
            try:
                # Collect metrics
                metrics = self._collect_metrics()
                
                # Log metrics
                self._log_metrics(metrics)
                
                # Sleep until next interval
                time.sleep(self.log_interval)
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(self.log_interval)
        
        logger.info("System monitor stopped")
    
    def _collect_metrics(self):
        """Collect system metrics"""
        metrics = {}
        
        # CPU metrics
        metrics['cpu_percent'] = psutil.cpu_percent(interval=1)
        metrics['cpu_count'] = psutil.cpu_count()
        
        # Memory metrics
        mem = psutil.virtual_memory()
        metrics['memory_percent'] = mem.percent
        metrics['memory_used_mb'] = mem.used / (1024 * 1024)
        metrics['memory_total_mb'] = mem.total / (1024 * 1024)
        
        # Temperature (RPi specific)
        try:
            temp = self._get_cpu_temperature()
            metrics['cpu_temp_c'] = temp
        except:
            metrics['cpu_temp_c'] = None
        
        # Disk usage
        disk = psutil.disk_usage('/')
        metrics['disk_percent'] = disk.percent
        metrics['disk_free_gb'] = disk.free / (1024 * 1024 * 1024)
        
        # Network statistics
        net = psutil.net_io_counters()
        metrics['bytes_sent'] = net.bytes_sent
        metrics['bytes_recv'] = net.bytes_recv
        
        return metrics
    
    def _get_cpu_temperature(self):
        """Get CPU temperature (RPi specific)"""
        try:
            # Try RPi thermal zone
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read()) / 1000.0
                return temp
        except:
            # Fallback to vcgencmd (requires root or video group)
            try:
                import subprocess
                result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                      capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    temp_str = result.stdout.strip()
                    temp = float(temp_str.split('=')[1].split("'")[0])
                    return temp
            except:
                pass
        return None
    
    def _log_metrics(self, metrics):
        """Log collected metrics"""
        log_msg = (
            f"System Health: "
            f"CPU {metrics['cpu_percent']:.1f}% "
        )
        
        if metrics['cpu_temp_c'] is not None:
            log_msg += f"({metrics['cpu_temp_c']:.1f}°C) "
        
        log_msg += (
            f"| Memory {metrics['memory_percent']:.1f}% "
            f"({metrics['memory_used_mb']:.0f}/{metrics['memory_total_mb']:.0f} MB) "
            f"| Disk {metrics['disk_percent']:.1f}% "
            f"({metrics['disk_free_gb']:.1f} GB free)"
        )
        
        logger.info(log_msg)
        
        # Warn on high usage
        if metrics['cpu_percent'] > 80:
            logger.warning(f"High CPU usage: {metrics['cpu_percent']:.1f}%")
        
        if metrics['memory_percent'] > 80:
            logger.warning(f"High memory usage: {metrics['memory_percent']:.1f}%")
        
        if metrics['cpu_temp_c'] and metrics['cpu_temp_c'] > 70:
            logger.warning(f"High CPU temperature: {metrics['cpu_temp_c']:.1f}°C")
    
    def stop(self):
        """Stop monitoring"""
        logger.info("Stopping system monitor...")
        self.running = False

if __name__ == "__main__":
    # Test standalone
    logging.basicConfig(level=logging.INFO)
    monitor = SystemMonitor(log_interval=5)
    monitor.run()
