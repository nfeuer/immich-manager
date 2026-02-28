"""
System monitoring functions for disk health, system metrics, and Docker containers
"""

import subprocess
import psutil
import docker
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime


class DiskMonitor:
    """Disk health monitoring using SMART data"""

    def __init__(self, devices: List[str]):
        """
        Initialize disk monitor

        Args:
            devices: List of device paths (e.g., ['/dev/sda', '/dev/sdb'])
        """
        self.devices = devices

    def check_smart_available(self) -> bool:
        """Check if smartctl is available"""
        try:
            subprocess.run(['smartctl', '--version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_disk_health(self, device: str) -> Dict[str, Any]:
        """
        Get SMART health data for a disk

        Args:
            device: Device path (e.g., '/dev/sda')

        Returns:
            Dictionary with health data
        """
        if not self.check_smart_available():
            return {
                'device': device,
                'error': 'smartctl not available',
                'smart_status': 'unknown'
            }

        try:
            # Get SMART data in JSON format
            result = subprocess.run(
                ['sudo', 'smartctl', '-a', '-j', device],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode not in [0, 4]:  # 4 means some SMART data available
                return {
                    'device': device,
                    'error': f'smartctl returned code {result.returncode}',
                    'smart_status': 'error'
                }

            data = json.loads(result.stdout)

            # Extract key metrics
            health = {
                'device': device,
                'smart_status': data.get('smart_status', {}).get('passed', False),
                'model': data.get('model_name', 'Unknown'),
                'serial': data.get('serial_number', 'Unknown'),
                'capacity': data.get('user_capacity', {}).get('bytes', 0),
                'temperature': None,
                'power_on_hours': None,
                'power_cycle_count': None,
                'reallocated_sectors': 0,
                'pending_sectors': 0,
                'uncorrectable_sectors': 0,
                'health_ok': True,
                'warnings': []
            }

            # Parse SMART attributes
            attrs = data.get('ata_smart_attributes', {}).get('table', [])
            for attr in attrs:
                attr_id = attr.get('id')
                attr_name = attr.get('name', '')
                raw_value = attr.get('raw', {}).get('value', 0)

                if attr_id == 194 or 'Temperature' in attr_name:
                    health['temperature'] = raw_value
                elif attr_id == 9 or 'Power_On_Hours' in attr_name:
                    health['power_on_hours'] = raw_value
                elif attr_id == 12 or 'Power_Cycle_Count' in attr_name:
                    health['power_cycle_count'] = raw_value
                elif attr_id == 5 or 'Reallocated_Sector' in attr_name:
                    health['reallocated_sectors'] = raw_value
                    if raw_value > 0:
                        health['health_ok'] = False
                        health['warnings'].append(f"Reallocated sectors: {raw_value}")
                elif attr_id == 197 or 'Current_Pending_Sector' in attr_name:
                    health['pending_sectors'] = raw_value
                    if raw_value > 0:
                        health['health_ok'] = False
                        health['warnings'].append(f"Pending sectors: {raw_value}")
                elif attr_id == 198 or 'Offline_Uncorrectable' in attr_name:
                    health['uncorrectable_sectors'] = raw_value
                    if raw_value > 0:
                        health['health_ok'] = False
                        health['warnings'].append(f"Uncorrectable sectors: {raw_value}")

            return health

        except subprocess.TimeoutExpired:
            return {
                'device': device,
                'error': 'smartctl timeout',
                'smart_status': 'timeout'
            }
        except json.JSONDecodeError:
            return {
                'device': device,
                'error': 'Failed to parse SMART data',
                'smart_status': 'parse_error'
            }
        except Exception as e:
            return {
                'device': device,
                'error': str(e),
                'smart_status': 'error'
            }

    def check_all_disks(self) -> List[Dict[str, Any]]:
        """Check health of all configured disks"""
        return [self.get_disk_health(device) for device in self.devices]


class SystemMonitor:
    """System resource monitoring"""

    def get_cpu_usage(self) -> float:
        """Get CPU usage percentage"""
        return psutil.cpu_percent(interval=1)

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage"""
        mem = psutil.virtual_memory()
        return {
            'percent': mem.percent,
            'used_gb': mem.used / (1024**3),
            'total_gb': mem.total / (1024**3),
            'available_gb': mem.available / (1024**3)
        }

    def get_disk_usage(self, path: str = '/') -> Dict[str, Any]:
        """Get disk usage for specified path"""
        disk = psutil.disk_usage(path)
        return {
            'percent': disk.percent,
            'used_gb': disk.used / (1024**3),
            'total_gb': disk.total / (1024**3),
            'free_gb': disk.free / (1024**3)
        }

    def get_network_usage(self) -> Dict[str, Any]:
        """Get network I/O"""
        net = psutil.net_io_counters()
        return {
            'sent_mb': net.bytes_sent / (1024**2),
            'recv_mb': net.bytes_recv / (1024**2)
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all system metrics"""
        memory = self.get_memory_usage()
        disk = self.get_disk_usage()
        network = self.get_network_usage()

        return {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': self.get_cpu_usage(),
            'memory_percent': memory['percent'],
            'memory_used_gb': memory['used_gb'],
            'memory_total_gb': memory['total_gb'],
            'disk_usage_percent': disk['percent'],
            'disk_used_gb': disk['used_gb'],
            'disk_total_gb': disk['total_gb'],
            'network_sent_mb': network['sent_mb'],
            'network_recv_mb': network['recv_mb']
        }


class DockerMonitor:
    """Docker container monitoring"""

    def __init__(self):
        """Initialize Docker monitor"""
        try:
            self.client = docker.from_env()
            self.available = True
        except Exception:
            self.client = None
            self.available = False

    def get_container_stats(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get stats for a specific container"""
        if not self.available:
            return None

        try:
            container = self.client.containers.get(container_name)
            stats = container.stats(stream=False)

            # Calculate CPU percentage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0

            # Get memory usage
            memory_mb = stats['memory_stats'].get('usage', 0) / (1024**2)

            return {
                'name': container_name,
                'status': container.status,
                'cpu_percent': cpu_percent,
                'memory_mb': memory_mb
            }
        except Exception as e:
            return {
                'name': container_name,
                'status': 'error',
                'error': str(e)
            }

    def get_immich_containers(self) -> List[Dict[str, Any]]:
        """Get all Immich-related containers"""
        if not self.available:
            return []

        try:
            containers = self.client.containers.list(filters={'name': 'immich'})
            return [
                {
                    'name': c.name,
                    'status': c.status,
                    'image': c.image.tags[0] if c.image.tags else 'unknown'
                }
                for c in containers
            ]
        except Exception:
            return []

    def check_immich_healthy(self) -> bool:
        """Check if Immich containers are healthy"""
        containers = self.get_immich_containers()
        if not containers:
            return False

        # Check if all containers are running
        return all(c['status'] == 'running' for c in containers)

    def stop_immich(self):
        """Stop all Immich containers."""
        if not self.available:
            return
        for c in self.client.containers.list(filters={"name": "immich"}):
            c.stop(timeout=30)

    def start_immich(self):
        """Start all stopped Immich containers."""
        if not self.available:
            return
        for c in self.client.containers.list(all=True, filters={"name": "immich"}):
            if c.status != "running":
                c.start()
