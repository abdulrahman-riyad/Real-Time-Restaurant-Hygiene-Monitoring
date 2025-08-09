#!/usr/bin/env python3
"""
System Test Script for Pizza Store Scooper Violation Detection
This script tests all components of the system to ensure they're working correctly.
"""

import time
import json
import asyncio
import httpx
import websockets
from typing import Dict, List, Optional
import sys
from datetime import datetime


class SystemTester:
    def __init__(self, api_url: str = "http://localhost:8000", ws_url: str = "ws://localhost:8000/ws"):
        self.api_url = api_url
        self.ws_url = ws_url
        self.test_results = []
        
    def print_header(self, text: str):
        """Print formatted header"""
        print("\n" + "=" * 60)
        print(f" {text}")
        print("=" * 60)
        
    def print_test(self, name: str, passed: bool, details: str = ""):
        """Print test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"     {details}")
        self.test_results.append({"name": name, "passed": passed, "details": details})
    
    async def test_health_check(self) -> bool:
        """Test if the streaming service is healthy"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/api/health", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    self.print_test("Health Check", True, f"Status: {data.get('status')}")
                    return True
                else:
                    self.print_test("Health Check", False, f"Status code: {response.status_code}")
                    return False
        except Exception as e:
            self.print_test("Health Check", False, f"Error: {str(e)}")
            return False
    
    async def test_websocket_connection(self) -> bool:
        """Test WebSocket connectivity"""
        try:
            async with websockets.connect(self.ws_url) as websocket:
                # Send a test message
                await websocket.send(json.dumps({"type": "ping"}))
                
                # Set a timeout for receiving
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Timeout is expected for ping, connection is still good
                    pass
                
                self.print_test("WebSocket Connection", True, "Connected successfully")
                return True
        except Exception as e:
            self.print_test("WebSocket Connection", False, f"Error: {str(e)}")
            return False
    
    async def test_start_stream(self, video_file: str = "test.mp4") -> Optional[str]:
        """Test starting a video stream"""
        try:
            stream_id = f"test_stream_{int(time.time())}"
            payload = {
                "file_path": video_file,
                "stream_id": stream_id
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/api/start-stream",
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    self.print_test("Start Stream", True, f"Stream ID: {stream_id}")
                    return stream_id
                else:
                    self.print_test("Start Stream", False, f"Status code: {response.status_code}")
                    return None
        except Exception as e:
            self.print_test("Start Stream", False, f"Error: {str(e)}")
            return None
    
    async def test_stop_stream(self) -> bool:
        """Test stopping a stream"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.api_url}/api/stop-stream", timeout=10.0)
                
                if response.status_code == 200:
                    self.print_test("Stop Stream", True, "Stream stopped successfully")
                    return True
                else:
                    self.print_test("Stop Stream", False, f"Status code: {response.status_code}")
                    return False
        except Exception as e:
            self.print_test("Stop Stream", False, f"Error: {str(e)}")
            return False
    
    async def test_get_violations(self) -> bool:
        """Test retrieving violations"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/api/violations", timeout=5.0)
                
                if response.status_code == 200:
                    violations = response.json()
                    self.print_test("Get Violations", True, f"Found {len(violations)} violations")
                    return True
                else:
                    self.print_test("Get Violations", False, f"Status code: {response.status_code}")
                    return False
        except Exception as e:
            self.print_test("Get Violations", False, f"Error: {str(e)}")
            return False
    
    async def test_stream_with_websocket(self, video_file: str = "test.mp4", duration: int = 5) -> bool:
        """Test streaming with WebSocket monitoring"""
        stream_id = None
        frames_received = 0
        violations_received = 0
        
        try:
            # Start stream
            stream_id = await self.test_start_stream(video_file)
            if not stream_id:
                return False
            
            # Connect to WebSocket and monitor
            async with websockets.connect(self.ws_url) as websocket:
                start_time = time.time()
                
                while time.time() - start_time < duration:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if data.get("type") == "detection_results":
                            frames_received += 1
                        elif data.get("type") == "violation_alert":
                            violations_received += 1
                            
                    except asyncio.TimeoutError:
                        continue
                    except json.JSONDecodeError:
                        continue
                
                # Stop stream
                await self.test_stop_stream()
                
                passed = frames_received > 0
                self.print_test(
                    "Stream Processing",
                    passed,
                    f"Received {frames_received} frames, {violations_received} violations in {duration}s"
                )
                return passed
                
        except Exception as e:
            self.print_test("Stream Processing", False, f"Error: {str(e)}")
            if stream_id:
                await self.test_stop_stream()
            return False
    
    async def run_all_tests(self, test_video: Optional[str] = None):
        """Run all system tests"""
        self.print_header("Pizza Store Violation Detection System Test")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"API URL: {self.api_url}")
        print(f"WebSocket URL: {self.ws_url}")
        
        self.print_header("Running Tests")
        
        # Basic connectivity tests
        await self.test_health_check()
        await self.test_websocket_connection()
        await self.test_get_violations()
        
        # Stream tests (if video provided)
        if test_video:
            print(f"\nTesting with video: {test_video}")
            await self.test_stream_with_websocket(test_video, duration=10)
        else:
            print("\nSkipping stream test (no video file specified)")
        
        # Print summary
        self.print_header("Test Summary")
        total = len(self.test_results)
        passed = sum(1 for t in self.test_results if t["passed"])
        failed = total - passed
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        
        if failed > 0:
            print("\nFailed Tests:")
            for test in self.test_results:
                if not test["passed"]:
                    print(f"  - {test['name']}: {test['details']}")
        
        return failed == 0


async def main():
    """Main test execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Pizza Store Violation Detection System")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API URL")
    parser.add_argument("--ws-url", default="ws://localhost:8000/ws", help="WebSocket URL")
    parser.add_argument("--video", help="Test video filename (should be in data/videos/)")
    
    args = parser.parse_args()
    
    tester = SystemTester(args.api_url, args.ws_url)
    success = await tester.run_all_tests(args.video)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        sys.exit(1)