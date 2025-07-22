"""
RTSP stream handler with reconnection and error handling
"""

import cv2
import numpy as np
import time
import threading
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import socket

logger = logging.getLogger(__name__)

@dataclass
class RTSPConfig:
    """RTSP stream configuration"""
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    transport: str = "tcp"  # tcp or udp
    timeout: int = 10
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 5
    buffer_size: int = 1

    def get_full_url(self) -> str:
        """Get full URL with credentials"""
        if self.username and self.password:
            # Insert credentials into URL
            protocol, rest = self.url.split("://", 1)
            return f"{protocol}://{self.username}:{self.password}@{rest}"
        return self.url

class RTSPHandler:
    """Handles RTSP stream with reconnection logic"""

    def __init__(self, config: RTSPConfig):
        self.config = config
        self.cap = None
        self.is_connected = False
        self.is_running = False
        self.reconnect_count = 0
        self.last_frame = None
        self.last_frame_time = None
        self.frame_count = 0
        self.error_count = 0
        self.callbacks = {
            'on_connect': None,
            'on_disconnect': None,
            'on_frame': None,
            'on_error': None
        }

    def set_callback(self, event: str, callback: Callable):
        """Set event callback"""
        if event in self.callbacks:
            self.callbacks[event] = callback

    def connect(self) -> bool:
        """Connect to RTSP stream"""
        try:
            logger.info(f"Connecting to RTSP stream: {self.config.url}")

            # Set up capture with transport protocol
            self.cap = cv2.VideoCapture(self.config.get_full_url())

            # Set capture properties
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)

            # Set transport protocol
            if self.config.transport == "tcp":
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('H', '2', '6', '4'))

            # Test connection
            if not self.cap.isOpened():
                raise Exception("Failed to open RTSP stream")

            # Try to read a test frame
            ret, frame = self.cap.read()
            if not ret or frame is None:
                raise Exception("Failed to read test frame")

            self.is_connected = True
            self.reconnect_count = 0
            self.last_frame = frame
            self.last_frame_time = time.time()

            # Trigger callback
            if self.callbacks['on_connect']:
                self.callbacks['on_connect']()

            logger.info(f"Successfully connected to RTSP stream")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to RTSP stream: {e}")
            self.is_connected = False

            if self.callbacks['on_error']:
                self.callbacks['on_error'](str(e))

            return False

    def disconnect(self):
        """Disconnect from RTSP stream"""
        if self.cap:
            self.cap.release()
            self.cap = None

        self.is_connected = False

        if self.callbacks['on_disconnect']:
            self.callbacks['on_disconnect']()

        logger.info("Disconnected from RTSP stream")

    def reconnect(self) -> bool:
        """Attempt to reconnect to stream"""
        self.disconnect()

        self.reconnect_count += 1
        if self.reconnect_count > self.config.max_reconnect_attempts:
            logger.error(f"Maximum reconnection attempts ({self.config.max_reconnect_attempts}) exceeded")
            return False

        logger.info(f"Reconnection attempt {self.reconnect_count}/{self.config.max_reconnect_attempts}")
        time.sleep(self.config.reconnect_delay)

        return self.connect()

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a frame from the stream"""
        if not self.is_connected or not self.cap:
            return None

        try:
            ret, frame = self.cap.read()

            if ret and frame is not None:
                self.last_frame = frame
                self.last_frame_time = time.time()
                self.frame_count += 1
                self.error_count = 0

                # Trigger callback
                if self.callbacks['on_frame']:
                    self.callbacks['on_frame'](frame)

                return frame
            else:
                self.error_count += 1

                # Check if we need to reconnect
                if self.error_count > 10:
                    logger.warning("Too many consecutive read errors, attempting reconnect")
                    if self.reconnect():
                        self.error_count = 0

                return None

        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            self.error_count += 1

            if self.callbacks['on_error']:
                self.callbacks['on_error'](str(e))

            return None

    def get_stream_info(self) -> Dict[str, Any]:
        """Get stream information"""
        info = {
            'url': self.config.url,
            'connected': self.is_connected,
            'frame_count': self.frame_count,
            'error_count': self.error_count,
            'reconnect_count': self.reconnect_count,
            'last_frame_time': self.last_frame_time
        }

        if self.cap and self.is_connected:
            info.update({
                'width': int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': self.cap.get(cv2.CAP_PROP_FPS),
                'backend': self.cap.getBackendName()
            })

        return info

    def check_stream_health(self) -> bool:
        """Check if stream is healthy"""
        if not self.is_connected:
            return False

        # Check if we've received frames recently
        if self.last_frame_time:
            time_since_last_frame = time.time() - self.last_frame_time
            if time_since_last_frame > self.config.timeout:
                logger.warning(f"No frames received for {time_since_last_frame:.1f} seconds")
                return False

        return True

    def start_monitoring(self):
        """Start background monitoring thread"""
        self.is_running = True
        monitor_thread = threading.Thread(target=self._monitor_stream, daemon=True)
        monitor_thread.start()

    def stop_monitoring(self):
        """Stop monitoring thread"""
        self.is_running = False

    def _monitor_stream(self):
        """Background thread to monitor stream health"""
        while self.is_running:
            if self.is_connected:
                if not self.check_stream_health():
                    logger.warning("Stream health check failed, attempting reconnect")
                    self.reconnect()

            time.sleep(5)  # Check every 5 seconds

class RTSPStreamManager:
    """Manages multiple RTSP streams"""

    def __init__(self):
        self.streams: Dict[str, RTSPHandler] = {}
        self.is_running = False

    def add_stream(self, stream_id: str, config: RTSPConfig) -> bool:
        """Add a new RTSP stream"""
        if stream_id in self.streams:
            logger.warning(f"Stream {stream_id} already exists")
            return False

        handler = RTSPHandler(config)
        if handler.connect():
            handler.start_monitoring()
            self.streams[stream_id] = handler
            logger.info(f"Added RTSP stream: {stream_id}")
            return True

        return False

    def remove_stream(self, stream_id: str):
        """Remove an RTSP stream"""
        if stream_id in self.streams:
            self.streams[stream_id].stop_monitoring()
            self.streams[stream_id].disconnect()
            del self.streams[stream_id]
            logger.info(f"Removed RTSP stream: {stream_id}")

    def get_frame(self, stream_id: str) -> Optional[np.ndarray]:
        """Get frame from a specific stream"""
        if stream_id not in self.streams:
            return None

        return self.streams[stream_id].read_frame()

    def get_all_stream_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all streams"""
        return {
            stream_id: handler.get_stream_info()
            for stream_id, handler in self.streams.items()
        }

    def cleanup(self):
        """Clean up all streams"""
        for stream_id in list(self.streams.keys()):
            self.remove_stream(stream_id)

# Example usage
if __name__ == "__main__":
    # Configure RTSP stream
    config = RTSPConfig(
        url="rtsp://192.168.1.100:554/stream",
        username="admin",
        password="password",
        transport="tcp"
    )

    # Create handler
    handler = RTSPHandler(config)

    # Set callbacks
    handler.set_callback('on_connect', lambda: print("Connected!"))
    handler.set_callback('on_disconnect', lambda: print("Disconnected!"))
    handler.set_callback('on_error', lambda e: print(f"Error: {e}"))

    # Connect and read frames
    if handler.connect():
        handler.start_monitoring()

        # Read frames for 30 seconds
        start_time = time.time()
        while time.time() - start_time < 30:
            frame = handler.read_frame()
            if frame is not None:
                # Process frame
                cv2.imshow("RTSP Stream", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.1)

        handler.stop_monitoring()
        handler.disconnect()
        cv2.destroyAllWindows()