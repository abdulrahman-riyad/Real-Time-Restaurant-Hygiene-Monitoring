#!/usr/bin/env python3
"""
Validation script to test the violation detection system
with the provided test videos and verify correct violation counts

Run this after starting all services with: docker-compose up
"""

import time
import json
import asyncio
import httpx
import websockets
from typing import Dict, List
import sys


class SystemValidator:
    def __init__(self):
        self.api_url = "http://localhost:8000"
        self.ws_url = "ws://localhost:8000/ws"
        
        # Expected violations for each test video
        self.expected_violations = {
            "Sah w b3dha ghalt.mp4": 1,
            "Sah w b3dha ghalt (2).mp4": 2,
            "Sah w b3dha ghalt (3).mp4": 1
        }
        
        self.test_results = {}
    
    async def test_video(self, video_file: str, expected_count: int) -> bool:
        """Test a single video and verify violation count"""
        print(f"\n{'='*60}")
        print(f"Testing: {video_file}")
        print(f"Expected violations: {expected_count}")
        print(f"{'='*60}")
        
        stream_id = f"test_{video_file.replace(' ', '_').replace('.mp4', '')}_{int(time.time())}"
        violations_detected = []
        frames_processed = 0
        
        try:
            # Start the stream
            print(f"Starting stream: {stream_id}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/api/start-stream",
                    json={"file_path": video_file, "stream_id": stream_id},
                    timeout=10.0
                )
                if response.status_code != 200:
                    print(f"❌ Failed to start stream: {response.status_code}")
                    return False
            
            # Connect to WebSocket and monitor
            print("Monitoring stream for violations...")
            async with websockets.connect(self.ws_url) as websocket:
                # Subscribe to stream
                await websocket.send(json.dumps({
                    "type": "subscribe",
                    "stream_id": stream_id
                }))
                
                start_time = time.time()
                last_update = time.time()
                
                # Monitor for up to 60 seconds or until video ends
                while time.time() - start_time < 60:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if data.get("type") == "detection_results":
                            frames_processed += 1
                            
                            # Update progress every 2 seconds
                            if time.time() - last_update > 2:
                                print(f"  Frames processed: {frames_processed}, Violations found: {len(violations_detected)}")
                                last_update = time.time()
                        
                        elif data.get("type") == "violation_alert":
                            violation = data.get("data", {})
                            if violation.get("stream_id") == stream_id:
                                violations_detected.append(violation)
                                print(f"  🚨 Violation detected: {violation.get('message', 'Unknown')}")
                    
                    except asyncio.TimeoutError:
                        # Check if stream has ended (no frames for 3 seconds)
                        if time.time() - last_update > 5:
                            print("  Stream appears to have ended")
                            break
                        continue
                    except Exception as e:
                        print(f"  Error receiving message: {e}")
                        continue
            
            # Stop the stream
            print("Stopping stream...")
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.api_url}/api/stop-stream", timeout=5.0)
            
            # Wait a moment for final violations to be processed
            await asyncio.sleep(2)
            
            # Get final violation count from API
            print("Fetching final violation count...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/api/violations", timeout=5.0)
                if response.status_code == 200:
                    all_violations = response.json()
                    stream_violations = [v for v in all_violations if v.get("stream_id") == stream_id]
                    if stream_violations:
                        violations_detected = stream_violations
            
            # Validate results
            actual_count = len(violations_detected)
            success = actual_count == expected_count
            
            print(f"\n{'='*40}")
            print(f"Results for {video_file}:")
            print(f"  Expected violations: {expected_count}")
            print(f"  Detected violations: {actual_count}")
            print(f"  Frames processed: {frames_processed}")
            
            if success:
                print(f"  ✅ TEST PASSED!")
            else:
                print(f"  ❌ TEST FAILED!")
                if actual_count < expected_count:
                    print(f"     Missing {expected_count - actual_count} violation(s)")
                else:
                    print(f"     Detected {actual_count - expected_count} extra violation(s)")
            
            print(f"{'='*40}")
            
            self.test_results[video_file] = {
                "expected": expected_count,
                "actual": actual_count,
                "success": success,
                "frames": frames_processed,
                "violations": violations_detected
            }
            
            return success
            
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            self.test_results[video_file] = {
                "expected": expected_count,
                "actual": 0,
                "success": False,
                "error": str(e)
            }
            return False
    
    async def run_all_tests(self):
        """Run tests for all videos"""
        print("\n" + "="*60)
        print("PIZZA STORE VIOLATION DETECTION SYSTEM VALIDATION")
        print("="*60)
        
        # Check if services are running
        print("\nChecking services...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/api/health", timeout=5.0)
                if response.status_code == 200:
                    print("✅ Services are running")
                else:
                    print("❌ Services not responding correctly")
                    return False
        except Exception as e:
            print(f"❌ Cannot connect to services: {e}")
            print("Make sure all services are running with: docker-compose up")
            return False
        
        # Test each video
        all_passed = True
        for video_file, expected_count in self.expected_violations.items():
            passed = await self.test_video(video_file, expected_count)
            if not passed:
                all_passed = False
            
            # Wait between tests
            await asyncio.sleep(3)
        
        # Print final summary
        print("\n" + "="*60)
        print("VALIDATION SUMMARY")
        print("="*60)
        
        for video_file, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} {video_file}: {result['actual']}/{result['expected']} violations")
            
            if not result["success"] and "error" not in result:
                # Print violation details for debugging
                for i, v in enumerate(result.get("violations", []), 1):
                    print(f"     Violation {i}: {v.get('message', 'Unknown')}")
        
        print("\n" + "="*60)
        if all_passed:
            print("🎉 ALL TESTS PASSED! System is working correctly!")
        else:
            print("⚠️  Some tests failed. Please check the violation detection logic.")
        print("="*60)
        
        return all_passed


async def main():
    """Main entry point"""
    validator = SystemValidator()
    success = await validator.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    print("Starting system validation...")
    print("This will test all three videos and verify violation counts.")
    print("Make sure all services are running before starting this test.")
    print("")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nValidation failed: {e}")
        sys.exit(1)