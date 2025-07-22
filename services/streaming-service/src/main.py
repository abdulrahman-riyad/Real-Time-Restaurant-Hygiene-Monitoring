import asyncio
import base64
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Dict, Any, List
from queue import Queue, Empty

import cv2
import httpx
import numpy as np
import pika
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
BROADCAST_FPS = 15  # The target FPS to send updates to the frontend

# --- Pydantic Models for API ---
class VideoRequest(BaseModel):
    file_path: str
    stream_id: str

# --- WebSocket Connection Management ---
class ConnectionManager:
    """Manages all active WebSocket connections."""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> str:
        client_id = str(uuid.uuid4())
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected.")
        return client_id

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected.")

    async def broadcast_json(self, data: dict):
        """Sends a JSON payload to all connected clients."""
        if not self.active_connections:
            return
            
        message = json.dumps(data)
        # Use asyncio.gather to send to all clients concurrently for performance
        await asyncio.gather(
            *(conn.send_text(message) for conn in self.active_connections.values()),
            return_exceptions=True  # Prevent one failed client from stopping others
        )

# --- Main Service Class ---
class StreamingService:
    """The core service that manages state, consumes messages, and broadcasts results."""
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.manager = ConnectionManager()
        self.violation_history = deque(maxlen=100)
        
        # This thread-safe queue is the bridge between the sync consumer and async main loop
        self.data_queue = Queue()
        
        # Decoupled state dictionaries
        self.latest_frames = {}
        self.latest_detections = defaultdict(dict)
        self.stream_stats = defaultdict(lambda: {'violations_count': 0, 'fps_counter': 0, 'last_fps_update': time.time(), 'fps': 0.0})

    def start_consumer_thread(self):
        """Starts the RabbitMQ consumer in a background thread."""
        thread = threading.Thread(target=self._run_consumer, daemon=True)
        thread.start()

    def _run_consumer(self):
        """This runs in a separate thread. Its ONLY job is to get messages and put them on the queue."""
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                channel = connection.channel()
                
                # Ensure both queues we listen to exist
                channel.queue_declare(queue='video_frames', durable=True)
                channel.queue_declare(queue='detection_results', durable=True)
                
                def callback(ch, method, properties, body):
                    # This is a synchronous function. It safely puts data onto the queue
                    # for the main async loop to process.
                    self.data_queue.put({'queue': method.routing_key, 'body': body})
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                channel.basic_consume(queue='video_frames', on_message_callback=callback)
                channel.basic_consume(queue='detection_results', on_message_callback=callback)

                logger.info("Starting RabbitMQ consumer...")
                channel.start_consuming()
            except pika.exceptions.AMQPConnectionError:
                logger.error("RabbitMQ connection failed. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"An unexpected error occurred in consumer: {e}. Restarting in 5 seconds...")
                time.sleep(5)

    def _get_class_color(self, class_name: str) -> tuple:
        """Helper to get a consistent color for each detected object class."""
        colors = {
            'person': (255, 165, 0), 'hand': (0, 0, 255), 'pizza': (128, 0, 128), 
            'scooper': (0, 255, 0), 'Hand': (0, 0, 255), 'Scooper': (0, 255, 0)
        }
        # Use .lower() to handle potential capitalization inconsistencies from the model
        return colors.get(class_name.lower(), (128, 128, 128))

    def _draw_on_frame(self, frame_b64: str, detections: List, violations: List, rois: List) -> str:
        """Draws all annotations on a frame."""
        try:
            img_data = base64.b64decode(frame_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                return frame_b64

            for roi in rois:
                coords = roi.get('coords', {})
                cv2.rectangle(frame, (int(coords['x1']), int(coords['y1'])), (int(coords['x2']), int(coords['y2'])), (255, 0, 0), 2)
                cv2.putText(frame, roi.get('name', 'ROI'), (int(coords['x1']), int(coords['y1']) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            for d in detections:
                bbox, name, conf = d.get('bbox'), d.get('class_name'), d.get('confidence')
                if not all([bbox, name, conf]): continue
                color = self._get_class_color(name)
                cv2.rectangle(frame, (int(bbox['x1']), int(bbox['y1'])), (int(bbox['x2']), int(bbox['y2'])), color, 2)
                label = f"{name}: {conf:.2f}"
                cv2.putText(frame, label, (int(bbox['x1']), int(bbox['y1']) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            for v in violations:
                bbox = v.get('bbox')
                if not bbox: continue
                cv2.rectangle(frame, (int(bbox['x1']), int(bbox['y1'])), (int(bbox['x2']), int(bbox['y2'])), (0, 0, 255), 4)
                cv2.putText(frame, "VIOLATION", (int(bbox['x1']), int(bbox['y1']) - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

            _, buffer = cv2.imencode('.jpg', frame)
            return base64.b64encode(buffer).decode('utf-8')
        except Exception:
            # If drawing fails for any reason, return the original raw frame to prevent crashes
            return frame_b64

    async def main_processing_loop(self):
        """
        The new main async loop. It safely gets data from the queue, processes state,
        combines data, and handles all async broadcasting.
        """
        while True:
            # Process all messages currently in the queue
            try:
                while not self.data_queue.empty():
                    item = self.data_queue.get_nowait()
                    body = item['body']
                    queue_name = item['queue']
                    data = json.loads(body)
                    stream_id = data.get('stream_id')
                    if not stream_id: continue

                    if queue_name == 'video_frames':
                        self.latest_frames[stream_id] = data.get('frame_data')
                    elif queue_name == 'detection_results':
                        self.latest_detections[stream_id] = data
                        if data.get('violations'):
                            for v in data['violations']:
                                record = {'id': str(uuid.uuid4()), 'stream_id': stream_id, **v}
                                self.violation_history.appendleft(record)
                                self.stream_stats[stream_id]['violations_count'] += 1
                                # This is now safe because we are in the main async loop
                                await self.manager.broadcast_json({'type': 'violation_alert', 'data': record})
            except Empty:
                pass # Queue is empty, which is normal
            except Exception as e:
                logger.error(f"Error in processing data from queue: {e}")

            # Now, broadcast the latest combined state for all active streams
            for stream_id in list(self.latest_frames.keys()):
                raw_frame = self.latest_frames.get(stream_id)
                detection_data = self.latest_detections.get(stream_id, {})
                
                if not raw_frame: continue

                stats = self.stream_stats[stream_id]
                stats['fps_counter'] += 1
                now = time.time()
                if now - stats['last_fps_update'] >= 1.0:
                    stats['fps'] = stats['fps_counter']
                    stats['fps_counter'] = 0
                    stats['last_fps_update'] = now
                
                annotated_frame = self._draw_on_frame(
                    raw_frame,
                    detection_data.get('detections', []),
                    detection_data.get('violations', []),
                    detection_data.get('rois', [])
                )
                
                message = {
                    'type': 'detection_results',
                    'stream_id': stream_id,
                    'data': {'annotated_frame_data': annotated_frame},
                    'stats': {'fps': stats['fps'], 'violations_count': stats['violations_count']}
                }
                await self.manager.broadcast_json(message)
            
            # Sleep to maintain the broadcast rate
            await asyncio.sleep(1 / BROADCAST_FPS)

# --- FastAPI App Setup ---
app = FastAPI(title="Streaming Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
service = StreamingService(os.getenv("RABBITMQ_URL"))

@app.on_event("startup")
async def startup_event():
    service.start_consumer_thread()
    # Start the main processing and broadcast loop
    asyncio.create_task(service.main_processing_loop())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = await service.manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Just keep the connection alive
    except WebSocketDisconnect:
        pass # Normal when client disconnects
    finally:
        service.manager.disconnect(client_id)

@app.post("/api/start-stream")
async def start_stream_proxy(request: VideoRequest):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://frame-reader:8001/start-stream", json=request.model_dump(), timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Frame processing service is unavailable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.json())

@app.post("/api/stop-stream")
async def stop_stream_proxy():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://frame-reader:8001/stop-stream", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Frame processing service is unavailable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.json())

@app.post("/api/flush-stream/{stream_id}")
async def flush_stream_data(stream_id: str):
    # This endpoint is kept for manual state clearing if needed
    if stream_id in service.stream_stats:
        del service.stream_stats[stream_id]
    if stream_id in service.latest_frames:
        del service.latest_frames[stream_id]
    if stream_id in service.latest_detections:
        del service.latest_detections[stream_id]
        
    current_violations = list(service.violation_history)
    service.violation_history.clear()
    for v in current_violations:
        if v.get('stream_id') != stream_id:
            service.violation_history.append(v)
            
    logger.info(f"Flushed all data for stream ID: {stream_id}")
    return {"status": "flushed", "stream_id": stream_id}

@app.get("/api/violations", response_model=List[Dict[str, Any]])
async def get_violations():
    return list(service.violation_history)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "active_ws_connections": len(service.manager.active_connections)}