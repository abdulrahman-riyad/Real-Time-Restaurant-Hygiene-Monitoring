#!/usr/bin/env python3
"""
Debug script to understand why violations aren't being detected
"""

import json
import time
import asyncio
import websockets

async def monitor_violations():
    """Monitor the WebSocket for detection data"""
    ws_url = "ws://localhost:8000/ws"
    
    print("Connecting to WebSocket...")
    async with websockets.connect(ws_url) as websocket:
        print("Connected! Monitoring for violations...")
        print("-" * 60)
        
        stats = {
            'frames': 0,
            'hands_in_roi': 0,
            'hands_with_scooper': 0,
            'hands_left_roi': 0,
            'hands_near_pizza': 0,
            'violations': 0
        }
        
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                data = json.loads(message)
                
                if data.get('type') == 'detection_results':
                    stats['frames'] += 1
                    
                    # Check detections
                    if 'data' in data:
                        detections = data['data'].get('detections', [])
                        
                        hands = [d for d in detections if 'hand' in d.get('class_name', '').lower()]
                        scoopers = [d for d in detections if 'scooper' in d.get('class_name', '').lower()]
                        pizzas = [d for d in detections if 'pizza' in d.get('class_name', '').lower()]
                        
                        # Rough ROI check (adjust based on your ROI)
                        for hand in hands:
                            center = hand.get('center', {})
                            x, y = center.get('x', 0), center.get('y', 0)
                            
                            # Check if in ROI (adjust these values to match your ROI)
                            if 50 <= x <= 350 and 150 <= y <= 400:
                                stats['hands_in_roi'] += 1
                                
                                # Check if scooper nearby
                                for scooper in scoopers:
                                    sc = scooper.get('center', {})
                                    dist = ((x - sc.get('x', 0))**2 + (y - sc.get('y', 0))**2)**0.5
                                    if dist < 200:
                                        stats['hands_with_scooper'] += 1
                                        break
                            
                            # Check if near pizza (lower part of frame)
                            if y > 300:
                                stats['hands_near_pizza'] += 1
                    
                elif data.get('type') == 'violation_alert':
                    stats['violations'] += 1
                    print(f"\n🚨 VIOLATION DETECTED: {data.get('data', {}).get('message', 'Unknown')}")
                
                # Print stats every 50 frames
                if stats['frames'] % 50 == 0:
                    print(f"\nStats after {stats['frames']} frames:")
                    print(f"  Hands in ROI: {stats['hands_in_roi']}")
                    print(f"  Hands with scooper: {stats['hands_with_scooper']}")
                    print(f"  Hands near pizza area: {stats['hands_near_pizza']}")
                    print(f"  Violations detected: {stats['violations']}")
                    print("-" * 60)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error: {e}")
                continue

if __name__ == "__main__":
    print("Violation Detection Debugger")
    print("=" * 60)
    print("This tool monitors the detection system to understand")
    print("why violations might not be triggering.")
    print("=" * 60)
    print("")
    
    try:
        asyncio.run(monitor_violations())
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure the system is running (docker-compose up)")