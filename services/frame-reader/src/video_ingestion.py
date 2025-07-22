"""
Video ingestion module for handling different video sources
"""

import cv2
import logging
from typing import Optional, Generator, Tuple, Dict, Any
from pathlib import Path
import numpy as np
from dataclasses import dataclass
from abc import ABC, abstractmethod
import time
import queue
import threading

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Video metadata information"""
    width: int
    height: int
    fps: float
    total_frames: int
    duration: float
    codec: str
    source_type: str
    source_path: str


class VideoSource(ABC):
    """Abstract base class for video sources"""

    @abstractmethod
    def open(self) -> bool:
        """Open the video source"""
        pass

    @abstractmethod
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from the source"""
        pass

    @abstractmethod
    def close(self):
        """Close the video source"""
        pass

    @abstractmethod
    def get_metadata(self) -> VideoMetadata:
        """Get video metadata"""
        pass


class FileVideoSource(VideoSource):
    """Video source for local files"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.cap = None
        self.metadata = None

    def open(self) -> bool:
        """Open video file"""
        try:
            self.cap = cv2.VideoCapture(self.file_path)
            if not self.cap.isOpened():
                logger.error(f"Failed to open video file: {self.file_path}")
                return False

            # Extract metadata
            self.metadata = VideoMetadata(
                width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=self.cap.get(cv2.CAP_PROP_FPS),
                total_frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                duration=self.cap.get(cv2.CAP_PROP_FRAME_COUNT) / self.cap.get(cv2.CAP_PROP_FPS),
                codec=self._get_codec(),
                source_type="file",
                source_path=self.file_path
            )

            logger.info(f"Opened video file: {self.file_path}")
            logger.info(f"Video metadata: {self.metadata}")
            return True

        except Exception as e:
            logger.error(f"Error opening video file: {e}")
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read next frame"""
        if self.cap is None:
            return False, None
        return self.cap.read()

    def close(self):
        """Close video file"""
        if self.cap:
            self.cap.release()
            logger.info(f"Closed video file: {self.file_path}")

    def get_metadata(self) -> VideoMetadata:
        """Get video metadata"""
        return self.metadata

    def seek(self, frame_number: int):
        """Seek to specific frame"""
        if self.cap:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    def _get_codec(self) -> str:
        """Get video codec"""
        try:
            fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            return codec
        except:
            return "unknown"


class RTSPVideoSource(VideoSource):
    """Video source for RTSP streams"""

    def __init__(self, rtsp_url: str, buffer_size: int = 1):
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.cap = None
        self.metadata = None

    def open(self) -> bool:
        """Open RTSP stream"""
        try:
            self.cap = cv2.VideoCapture(self.rtsp_url)

            # Set buffer size for low latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)

            if not self.cap.isOpened():
                logger.error(f"Failed to open RTSP stream: {self.rtsp_url}")
                return False

            # Extract metadata
            self.metadata = VideoMetadata(
                width=int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=self.cap.get(cv2.CAP_PROP_FPS) or 30.0,  # Default to 30 if not available
                total_frames=-1,  # Unknown for streams
                duration=-1,  # Unknown for streams
                codec=self._get_codec(),
                source_type="rtsp",
                source_path=self.rtsp_url
            )

            logger.info(f"Opened RTSP stream: {self.rtsp_url}")
            return True

        except Exception as e:
            logger.error(f"Error opening RTSP stream: {e}")
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read next frame"""
        if self.cap is None:
            return False, None
        return self.cap.read()

    def close(self):
        """Close RTSP stream"""
        if self.cap:
            self.cap.release()
            logger.info(f"Closed RTSP stream: {self.rtsp_url}")

    def get_metadata(self) -> VideoMetadata:
        """Get stream metadata"""
        return self.metadata

    def _get_codec(self) -> str:
        """Get video codec"""
        try:
            fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            return codec
        except:
            return "h264"  # Common for RTSP


class VideoIngestion:
    """Main video ingestion handler"""

    def __init__(self):
        self.sources: Dict[str, VideoSource] = {}
        self.active_streams: Dict[str, bool] = {}

    def add_file_source(self, stream_id: str, file_path: str) -> bool:
        """Add a file video source"""
        if not Path(file_path).exists():
            logger.error(f"Video file not found: {file_path}")
            return False

        source = FileVideoSource(file_path)
        if source.open():
            self.sources[stream_id] = source
            self.active_streams[stream_id] = True
            return True
        return False

    def add_rtsp_source(self, stream_id: str, rtsp_url: str) -> bool:
        """Add an RTSP video source"""
        source = RTSPVideoSource(rtsp_url)
        if source.open():
            self.sources[stream_id] = source
            self.active_streams[stream_id] = True
            return True
        return False

    def remove_source(self, stream_id: str):
        """Remove a video source"""
        if stream_id in self.sources:
            self.sources[stream_id].close()
            del self.sources[stream_id]
            del self.active_streams[stream_id]
            logger.info(f"Removed video source: {stream_id}")

    def get_frame(self, stream_id: str) -> Tuple[bool, Optional[np.ndarray]]:
        """Get next frame from a stream"""
        if stream_id not in self.sources:
            return False, None

        return self.sources[stream_id].read()

    def get_metadata(self, stream_id: str) -> Optional[VideoMetadata]:
        """Get metadata for a stream"""
        if stream_id not in self.sources:
            return None

        return self.sources[stream_id].get_metadata()

    def is_active(self, stream_id: str) -> bool:
        """Check if stream is active"""
        return self.active_streams.get(stream_id, False)

    def stop_stream(self, stream_id: str):
        """Stop a stream"""
        if stream_id in self.active_streams:
            self.active_streams[stream_id] = False

    def start_stream(self, stream_id: str):
        """Start a stream"""
        if stream_id in self.active_streams:
            self.active_streams[stream_id] = True

    def get_all_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all streams"""
        streams = {}
        for stream_id, source in self.sources.items():
            metadata = source.get_metadata()
            streams[stream_id] = {
                'active': self.active_streams[stream_id],
                'source_type': metadata.source_type,
                'source_path': metadata.source_path,
                'resolution': f"{metadata.width}x{metadata.height}",
                'fps': metadata.fps
            }
        return streams

    def cleanup(self):
        """Clean up all sources"""
        for stream_id in list(self.sources.keys()):
            self.remove_source(stream_id)


class BufferedVideoReader:
    """Buffered video reader for smooth playback"""

    def __init__(self, source: VideoSource, buffer_size: int = 30):
        self.source = source
        self.buffer_size = buffer_size
        self.frame_buffer = queue.Queue(maxsize=buffer_size)
        self.reading = False
        self.reader_thread = None

    def start(self):
        """Start buffered reading"""
        self.reading = True
        self.reader_thread = threading.Thread(target=self._read_frames, daemon=True)
        self.reader_thread.start()
        logger.info("Started buffered video reader")

    def stop(self):
        """Stop buffered reading"""
        self.reading = False
        if self.reader_thread:
            self.reader_thread.join()
        logger.info("Stopped buffered video reader")

    def _read_frames(self):
        """Background thread to read frames"""
        while self.reading:
            ret, frame = self.source.read()
            if ret and frame is not None:
                try:
                    self.frame_buffer.put(frame, timeout=0.1)
                except queue.Full:
                    # Drop oldest frame if buffer is full
                    try:
                        self.frame_buffer.get_nowait()
                        self.frame_buffer.put(frame, timeout=0.1)
                    except:
                        pass
            else:
                time.sleep(0.01)

    def get_frame(self) -> Optional[np.ndarray]:
        """Get frame from buffer"""
        try:
            return self.frame_buffer.get(timeout=0.1)
        except queue.Empty:
            return None

    def get_buffer_size(self) -> int:
        """Get current buffer size"""
        return self.frame_buffer.qsize()