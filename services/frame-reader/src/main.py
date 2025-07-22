import asyncio
import base64
import json
import logging
import os
import time

import cv2
import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
TARGET_PROCESSING_FPS = 10  # Process 10 frames per second to avoid overwhelming the detection service

# --- Pydantic Model for API Request Body ---
class StreamRequest(BaseModel):
    file_path: str
    stream_id: str

# --- Main Service Class ---
class FrameReader:
    """
    This class manages the video processing task. It is designed as a "singleton" streamer,
    meaning it can only process one video at a time, ensuring clean starts and stops.
    """
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.active_stream_task = None  # This will hold the single running asyncio.Task
        self._connect_rabbitmq()

    def _connect_rabbitmq(self):
        """
        Establishes a robust connection to RabbitMQ with a retry loop.
        This function is complete and correct.
        """
        max_retries = 10
        for i in range(max_retries):
            try:
                self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                self.channel = self.connection.channel()
                self.channel.queue_declare(queue='video_frames', durable=True)
                logger.info("FrameReader connected to RabbitMQ.")
                return
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection failed (attempt {i+1}/{max_retries}): {e}")
                time.sleep(5)
        raise Exception("FrameReader failed to connect to RabbitMQ after multiple retries.")

    def publish_frame(self, frame_data: dict):
        """
        Publishes a single frame to RabbitMQ, with reconnection logic.
        This function is complete and correct.
        """
        try:
            if not self.connection or self.connection.is_closed:
                logger.warning("RabbitMQ connection lost. Attempting to reconnect...")
                self._connect_rabbitmq()

            self.channel.basic_publish(
                exchange='',
                routing_key='video_frames',
                body=json.dumps(frame_data),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        except Exception as e:
            logger.error(f"Failed to publish frame: {e}")

    async def _video_processing_loop(self, file_path: str, stream_id: str):
        """The core async task that reads a video file and publishes frames."""
        video_path = f"/app/videos/{file_path}"
        cap = None
        try:
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Failed to open video file: {video_path}")
                return

            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frame_count = 0
            logger.info(f"Task started for stream '{stream_id}' from '{file_path}'")

            while True:
                # This loop will be broken externally by task cancellation
                ret, frame = cap.read()
                if not ret:
                    logger.info(f"End of video '{file_path}', looping.")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_resized = cv2.resize(frame, (640, 480))
                _, buffer = cv2.imencode('.jpg', frame_resized)
                frame_b64 = base64.b64encode(buffer).decode('utf-8')

                frame_data = {
                    'stream_id': stream_id,
                    'frame_id': f"{stream_id}_{frame_count}",
                    'timestamp': time.time(),
                    'frame_data': frame_b64,
                }
                self.publish_frame(frame_data)
                frame_count += 1

                # Sleep to control the rate of publishing frames
                await asyncio.sleep(1 / TARGET_PROCESSING_FPS)

        except asyncio.CancelledError:
            # This is the expected way to stop the loop
            logger.info(f"Processing loop for stream '{stream_id}' was cancelled.")
        except Exception as e:
            logger.error(f"An error occurred in the processing loop for '{stream_id}': {e}", exc_info=True)
        finally:
            # This block ensures the video file is always released
            if cap and cap.isOpened():
                cap.release()
            logger.info(f"Cleaned up video resources for stream '{stream_id}'.")

    async def start_stream(self, file_path: str, stream_id: str):
        """Public method to start a new stream. It guarantees any old stream is stopped first."""
        await self.stop_stream()  # Ensure a clean state by stopping any previous task
        
        logger.info(f"Creating new processing task for stream ID: {stream_id}")
        self.active_stream_task = asyncio.create_task(self._video_processing_loop(file_path, stream_id))
        return {"status": "processing_started", "stream_id": stream_id}

    async def stop_stream(self):
        """Public method to gracefully stop the currently active stream task."""
        if self.active_stream_task and not self.active_stream_task.done():
            logger.info("Stopping active stream task...")
            self.active_stream_task.cancel()
            # Wait for the task to acknowledge the cancellation
            try:
                await self.active_stream_task
            except asyncio.CancelledError:
                pass
            self.active_stream_task = None
            logger.info("Active stream task stopped.")
            return {"status": "stream_stopped"}
        return {"status": "no_active_stream_to_stop"}

# --- FastAPI Application Setup ---
app = FastAPI(title="Frame Reader Service")
rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/")
frame_reader = FrameReader(rabbitmq_url=rabbitmq_url)

@app.post("/start-stream")
async def start_stream_endpoint(request: StreamRequest):
    """API endpoint to start processing a video."""
    if frame_reader.active_stream_task and not frame_reader.active_stream_task.done():
        raise HTTPException(status_code=409, detail="A stream is already in progress. Please stop it before starting a new one.")
    
    # We can await the start_stream method directly. No background task needed here
    # as the method itself creates a background asyncio task.
    return await frame_reader.start_stream(request.file_path, request.stream_id)

@app.post("/stop-stream")
async def stop_stream_endpoint():
    """API endpoint to stop the current video processing."""
    return await frame_reader.stop_stream()