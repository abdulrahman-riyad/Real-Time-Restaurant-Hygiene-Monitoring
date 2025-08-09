#!/usr/bin/env python3
"""
Real-time System Monitor for Pizza Store Violation Detection
Monitors all services and displays live statistics.
"""

import asyncio
import json
import time
import httpx
import websockets
from datetime import datetime
from typing import Dict, Any
import os
import sys
from collections import deque


class SystemMonitor:
    def __init__(self):
        self.api_url = "http://localhost:8000"
        self.ws_url = "ws://localhost:8000/ws"
        self.stats = {
            'start_time': time.time(),
            'frames_processed': 0,
            'violations_detected': 0,
            'websocket_connected': False,
            'last_frame_time': None,
            'fps_history': deque(maxlen=30),
            'active_stream': None,
            'services_status': {}
        }
        
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
    def format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        
    def print_dashboard(self):
        """Print monitoring dashboard"""
        self.clear_screen()
        
        uptime = time.time() - self.stats['start_time']
        avg_fps = sum(self.stats['fps_history']) / len(self.stats['fps_history']) if self.stats['fps_history'] else 0
        
        print("=" * 70)
        print(" PIZZA STORE VIOLATION DETECTION - SYSTEM MONITOR")
        print("=" * 70)
        print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  Uptime: {self.format_uptime(uptime)}")
        print("-" * 70)
        
        # Service Status
        print("\n📊 SERVICE STATUS:")
        print("-" * 40)
        
        services = [
            ('RabbitMQ', self.stats['services_status'].get('rabbitmq', 'Unknown')),
            ('Frame Reader', self.stats['services_status'].get('frame_reader', 'Unknown')),
            ('Detection Service', self.stats['services_status'].get('detection', 'Unknown')),
            ('Streaming Service', self.stats['services_status'].get('streaming', 'Unknown')),
            ('Frontend', self.stats['services_status'].get('frontend', 'Unknown')),
        ]
        
        for service, status in services:
            status_icon = "✅" if status == "Running" else "❌" if status == "Error" else "⚠️"
            print(f"  {status_icon} {service:20s} : {status}")
        
        # Performance Metrics
        print("\n📈 PERFORMANCE METRICS:")
        print("-" * 40)
        print(f"  Current FPS        : {self.stats['fps_history'][-1] if self.stats['fps_history'] else 0:.1f}")
        print(f"  Average FPS        : {avg_fps:.1f}")
        print(f"  Frames Processed   : {self.stats['frames_processed']:,}")
        print(f"  Processing Rate    : {self.stats['frames_processed'] / uptime if uptime > 0 else 0:.1f} frames/sec")
        
        # Violation Statistics
        print("\n🚨 VIOLATION STATISTICS:")
        print("-" * 40)
        print(f"  Total Violations   : {self.stats['violations_detected']}")
        print(f"  Violation Rate     : {self.stats['violations_detected'] / (self.stats['frames_processed'] / 100) if self.stats['frames_processed'] > 0 else 0:.2f}%")
        print(f"  Last Violation     : {self.stats.get('last_violation_time', 'None')}")
        
        # Stream Information
        print("\n📹 STREAM INFORMATION:")
        print("-" * 40)
        print(f"  Active Stream      : {self.stats['active_stream'] or 'None'}")
        print(f"  WebSocket Status   : {'Connected' if self.stats['websocket_connected'] else 'Disconnected'}")
        print(f"  Last Frame         : {self.stats['last_frame_time'] or 'Never'}")
        
        # System Health
        print("\n💚 SYSTEM HEALTH:")
        print("-" * 40)
        
        if self.stats['websocket_connected'] and avg_fps > 5:
            print("  Status: HEALTHY - All systems operational")
        elif self.stats['websocket_connected']:
            print("  Status: DEGRADED - Low frame rate")
        else:
            print("  Status: ERROR - WebSocket disconnected")
        
        print("\n" + "=" * 70)
        print(" Press Ctrl+C to exit")
        
    async def check_service_health(self):
        """Check health of all services"""
        # Check Streaming Service
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/api/health", timeout=2.0)
                if response.status_code == 200:
                    self.stats['services_status']['streaming'] = "Running"
                else:
                    self.stats['services_status']['streaming'] = "Error"
        except:
            self.stats['services_status']['streaming'] = "Offline"
        
        # Check Frontend (port 3000)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:3000", timeout=2.0)
                if response.status_code in [200, 304]:
                    self.stats['services_status']['frontend'] = "Running"
                else:
                    self.stats['services_status']['frontend'] = "Error"
        except:
            self.stats['services_status']['frontend'] = "Offline"
        
        # Check RabbitMQ Management
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://admin:admin@localhost:15672/api/overview", timeout=2.0)
                if response.status_code == 200:
                    self.stats['services_status']['rabbitmq'] = "Running"
                else:
                    self.stats['services_status']['rabbitmq'] = "Error"
        except:
            self.stats['services_status']['rabbitmq'] = "Offline"
        
        # Infer other services based on data flow
        if self.stats['frames_processed'] > 0:
            self.stats['services_status']['frame_reader'] = "Running"
            self.stats['services_status']['detection'] = "Running"
        else:
            if self.stats['services_status'].get('rabbitmq') == "Running":
                self.stats['services_status']['frame_reader'] = "Idle"
                self.stats['services_status']['detection'] = "Idle"
            else:
                self.stats['services_status']['frame_reader'] = "Unknown"
                self.stats['services_status']['detection'] = "Unknown"
    
    async def monitor_websocket(self):
        """Monitor WebSocket for real-time data"""
        while True:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.stats['websocket_connected'] = True
                    frame_count = 0
                    last_fps_calc = time.time()
                    
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            data = json.loads(message)
                            
                            if data.get('type') == 'detection_results':
                                self.stats['frames_processed'] += 1
                                frame_count += 1
                                self.stats['last_frame_time'] = datetime.now().strftime('%H:%M:%S')
                                self.stats['active_stream'] = data.get('stream_id', 'Unknown')
                                
                                # Calculate FPS
                                current_time = time.time()
                                if current_time - last_fps_calc >= 1.0:
                                    fps = frame_count / (current_time - last_fps_calc)
                                    self.stats['fps_history'].append(fps)
                                    frame_count = 0
                                    last_fps_calc = current_time
                                
                            elif data.get('type') == 'violation_alert':
                                self.stats['violations_detected'] += 1
                                self.stats['last_violation_time'] = datetime.now().strftime('%H:%M:%S')
                                
                        except asyncio.TimeoutError:
                            # No data received, but connection still alive
                            continue
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                self.stats['websocket_connected'] = False
                await asyncio.sleep(5)  # Wait before reconnecting
    
    async def periodic_health_check(self):
        """Periodically check service health"""
        while True:
            await self.check_service_health()
            await asyncio.sleep(10)  # Check every 10 seconds
    
    async def periodic_display(self):
        """Periodically update display"""
        while True:
            self.print_dashboard()
            await asyncio.sleep(1)  # Update display every second
    
    async def run(self):
        """Run all monitoring tasks"""
        # Initial health check
        await self.check_service_health()
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self.monitor_websocket()),
            asyncio.create_task(self.periodic_health_check()),
            asyncio.create_task(self.periodic_display())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
            for task in tasks:
                task.cancel()


async def main():
    """Main monitoring function"""
    print("Starting system monitor...")
    print("Connecting to services...")
    
    monitor = SystemMonitor()
    
    try:
        await monitor.run()
    except KeyboardInterrupt:
        print("\n\nMonitor stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nMonitor error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMonitor interrupted")
        sys.exit(0)