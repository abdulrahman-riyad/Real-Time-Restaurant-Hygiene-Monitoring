"""
File: /services/streaming-service/src/main.py
Simplified streaming service with all type issues fixed
"""

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
import pika.exceptions
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
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        return client_id

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected. Remaining connections: {len(self.active_connections)}")

    async def broadcast_json(self, data: dict):
        """Sends a JSON payload to all connected clients."""
        if not self.active_connections:
            return
            
        message = json.dumps(data)
        disconnected_clients = []
        
        # Send to all clients, tracking any that fail
        results = await asyncio.gather(
            *(conn.send_text(message) for conn in self.active_connections.values()),
            return_exceptions=True
        )
        
        # Clean up any disconnected clients
        for client_id, result in zip(list(self.active_connections.keys()), results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to send to client {client_id}: {result}")
                disconnected_clients.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

# --- Main Service Class ---
class StreamingService:
    """The core service that manages state, consumes messages, and broadcasts results."""
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.manager = ConnectionManager()
        self.violation_history = deque(maxlen=100)
        
        # Thread-safe queue for sync/async bridge
        self.data_queue = Queue()
        
        # State management
        self.latest_frames: Dict[str, str] = {}
        self.latest_detections: Dict[str, dict] = defaultdict(dict)
        self.stream_stats = defaultdict(lambda: {
            'violations_count': 0, 
            'fps_counter': 0, 
            'last_fps_update': time.time(), 
            'fps': 0.0
        })

    def start_consumer_thread(self):
        """Starts the RabbitMQ consumer in a background thread."""
        thread = threading.Thread(target=self._run_consumer, daemon=True)
        thread.start()
        logger.info("Started RabbitMQ consumer thread")

    def _run_consumer(self):
        """Runs in a separate thread. Gets messages and puts them on the queue."""
        retry_count = 0
        max_retries = 5
        
        while True:
            connection = None
            channel = None
            
            try:
                # Create connection with retry logic
                logger.info(f"Connecting to RabbitMQ at {self.rabbitmq_url}")
                connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                channel = connection.channel()
                
                # Declare queues
                channel.queue_declare(queue='video_frames', durable=True)
                channel.queue_declare(queue='detection_results', durable=True)
                
                # Define callback function
                def callback(ch, method, properties, body):
                    try:
                        # Put data on queue for async processing
                        self.data_queue.put({
                            'queue': method.routing_key, 
                            'body': body
                        })
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                # Set up consumers
                channel.basic_consume(queue='video_frames', on_message_callback=callback)
                channel.basic_consume(queue='detection_results', on_message_callback=callback)

                logger.info("✅ RabbitMQ consumer started successfully")
                retry_count = 0  # Reset retry count on successful connection
                
                # Start consuming
                channel.start_consuming()
                
            except pika.exceptions.AMQPConnectionError as e:
                retry_count += 1
                wait_time = min(5 * retry_count, 30)  # Exponential backoff up to 30 seconds
                logger.error(f"RabbitMQ connection failed (attempt {retry_count}): {e}")
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Unexpected error in consumer: {e}", exc_info=True)
                time.sleep(5)
            
            finally:
                # Clean up connections
                try:
                    if channel:
                        channel.close()
                    if connection:
                        connection.close()
                except:
                    pass

    def _get_class_color(self, class_name: str) -> tuple:
        """Get consistent color for each detected object class."""
        colors = {
            'person': (255, 165, 0),  # Orange
            'hand': (0, 0, 255),      # Red
            'pizza': (128, 0, 128),   # Purple
            'scooper': (0, 255, 0),   # Green
        }
        # Handle case variations
        return colors.get(class_name.lower(), (128, 128, 128))  # Gray default

    def _draw_on_frame(self, frame_b64: str, detections: List, violations: List, rois: List) -> str:
        """Draws all annotations on a frame."""
        try:
            # Decode base64 frame
            img_data = base64.b64decode(frame_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                logger.warning("Failed to decode frame for annotation")
                return frame_b64

            # Draw ROIs (Regions of Interest)
            for roi in rois:
                coords = roi.get('coords', {})
                if coords and all(k in coords for k in ['x1', 'y1', 'x2', 'y2']):
                    try:
                        cv2.rectangle(
                            frame, 
                            (int(coords['x1']), int(coords['y1'])), 
                            (int(coords['x2']), int(coords['y2'])), 
                            (255, 0, 0), 2  # Blue for ROI
                        )
                        cv2.putText(
                            frame, 
                            roi.get('name', 'ROI'), 
                            (int(coords['x1']), int(coords['y1']) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2
                        )
                    except:
                        pass

            # Draw detections
            for d in detections:
                try:
                    bbox = d.get('bbox')
                    name = d.get('class_name')
                    conf = d.get('confidence')
                    
                    # Skip if missing required fields
                    if not bbox or not name or conf is None:
                        continue
                    
                    # Check bbox has all required keys
                    if not all(k in bbox for k in ['x1', 'y1', 'x2', 'y2']):
                        continue
                    
                    color = self._get_class_color(name)
                    cv2.rectangle(
                        frame, 
                        (int(bbox['x1']), int(bbox['y1'])), 
                        (int(bbox['x2']), int(bbox['y2'])), 
                        color, 2
                    )
                    label = f"{name}: {conf:.2f}"
                    cv2.putText(
                        frame, label, 
                        (int(bbox['x1']), int(bbox['y1']) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                    )
                except Exception as e:
                    logger.debug(f"Error drawing detection: {e}")
                    continue

            # Draw violations (with thicker red boxes)
            for v in violations:
                try:
                    bbox = v.get('bbox')
                    if bbox and all(k in bbox for k in ['x1', 'y1', 'x2', 'y2']):
                        cv2.rectangle(
                            frame, 
                            (int(bbox['x1']), int(bbox['y1'])), 
                            (int(bbox['x2']), int(bbox['y2'])), 
                            (0, 0, 255), 4  # Thick red for violations
                        )
                        cv2.putText(
                            frame, "VIOLATION", 
                            (int(bbox['x1']), int(bbox['y1']) - 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA
                        )
                except:
                    pass

            # Encode back to base64
            # Fix for the buffer type issue
            success, buffer = cv2.imencode('.jpg', frame)
            if success:
                # Convert numpy array to bytes properly
                frame_bytes = buffer.tobytes()
                return base64.b64encode(frame_bytes).decode('utf-8')
            else:
                return frame_b64
            
        except Exception as e:
            logger.error(f"Error drawing annotations: {e}")
            return frame_b64  # Return original on error

    async def main_processing_loop(self):
        """Main async loop for processing and broadcasting."""
        logger.info("Starting main processing loop")
        
        while True:
            try:
                # Process all messages currently in queue
                messages_processed = 0
                max_messages_per_cycle = 10  # Prevent blocking too long
                
                while not self.data_queue.empty() and messages_processed < max_messages_per_cycle:
                    try:
                        item = self.data_queue.get_nowait()
                        body = item['body']
                        queue_name = item['queue']
                        
                        # Parse message
                        data = json.loads(body)
                        stream_id = data.get('stream_id')
                        
                        if not stream_id:
                            continue
                        
                        # Process based on queue type
                        if queue_name == 'video_frames':
                            self.latest_frames[stream_id] = data.get('frame_data')
                            
                        elif queue_name == 'detection_results':
                            self.latest_detections[stream_id] = data
                            
                            # Handle violations
                            if data.get('violations'):
                                for v in data['violations']:
                                    record = {
                                        'id': str(uuid.uuid4()), 
                                        'stream_id': stream_id,
                                        'timestamp': time.time(),
                                        **v
                                    }
                                    self.violation_history.appendleft(record)
                                    self.stream_stats[stream_id]['violations_count'] += 1
                                    
                                    # Broadcast violation alert
                                    await self.manager.broadcast_json({
                                        'type': 'violation_alert', 
                                        'data': record
                                    })
                                    logger.info(f"Violation detected in stream {stream_id}")
                        
                        messages_processed += 1
                        
                    except Empty:
                        break
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

                # Broadcast current state for all active streams
                for stream_id in list(self.latest_frames.keys()):
                    raw_frame = self.latest_frames.get(stream_id)
                    detection_data = self.latest_detections.get(stream_id, {})
                    
                    if not raw_frame:
                        continue

                    # Update FPS stats
                    stats = self.stream_stats[stream_id]
                    stats['fps_counter'] += 1
                    now = time.time()
                    
                    if now - stats['last_fps_update'] >= 1.0:
                        stats['fps'] = stats['fps_counter']
                        stats['fps_counter'] = 0
                        stats['last_fps_update'] = now
                    
                    # Draw annotations
                    annotated_frame = self._draw_on_frame(
                        raw_frame,
                        detection_data.get('detections', []),
                        detection_data.get('violations', []),
                        detection_data.get('rois', [])
                    )
                    
                    # Prepare and send message
                    message = {
                        'type': 'detection_results',
                        'stream_id': stream_id,
                        'data': {'annotated_frame_data': annotated_frame},
                        'stats': {
                            'fps': stats['fps'], 
                            'violations_count': stats['violations_count']
                        }
                    }
                    await self.manager.broadcast_json(message)
                
                # Control broadcast rate
                await asyncio.sleep(1 / BROADCAST_FPS)
                
            except Exception as e:
                logger.error(f"Error in main processing loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)  # Brief pause before continuing

# --- FastAPI App Setup ---
app = FastAPI(title="Streaming Service")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

service = StreamingService(os.getenv("RABBITMQ_URL", "amqp://admin:admin@rabbitmq:5672/"))

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting Streaming Service")
    service.start_consumer_thread()
    asyncio.create_task(service.main_processing_loop())
    logger.info("Streaming Service started successfully")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming."""
    client_id = await service.manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        service.manager.disconnect(client_id)

@app.post("/api/start-stream")
async def start_stream_proxy(request: VideoRequest):
    """Proxy to frame-reader service to start a stream."""
    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://frame-reader:8001/start-stream", 
                    json=request.model_dump(), 
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"Stream started: {request.stream_id}")
                return response.json()
                
        except httpx.ConnectError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Frame reader not ready, retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Frame reader service unavailable after {max_retries} attempts")
                raise HTTPException(
                    status_code=503, 
                    detail="Frame processing service is unavailable. Please try again."
                )
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error from frame reader: {exc.response.status_code}")
            raise HTTPException(
                status_code=exc.response.status_code, 
                detail=exc.response.json()
            )
        except Exception as e:
            logger.error(f"Unexpected error starting stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stop-stream")
async def stop_stream_proxy():
    """Proxy to frame-reader service to stop a stream."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://frame-reader:8001/stop-stream", 
                timeout=10.0
            )
            response.raise_for_status()
            logger.info("Stream stopped")
            return response.json()
    except httpx.RequestError:
        logger.error("Failed to stop stream - frame reader unavailable")
        raise HTTPException(
            status_code=503, 
            detail="Frame processing service is unavailable."
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code, 
            detail=exc.response.json()
        )

@app.post("/api/flush-stream/{stream_id}")
async def flush_stream_data(stream_id: str):
    """Clear all data for a specific stream."""
    # Clear stats
    if stream_id in service.stream_stats:
        del service.stream_stats[stream_id]
    
    # Clear frames
    if stream_id in service.latest_frames:
        del service.latest_frames[stream_id]
    
    # Clear detections
    if stream_id in service.latest_detections:
        del service.latest_detections[stream_id]
    
    # Clear violations for this stream
    current_violations = list(service.violation_history)
    service.violation_history.clear()
    for v in current_violations:
        if v.get('stream_id') != stream_id:
            service.violation_history.append(v)
    
    logger.info(f"Flushed all data for stream ID: {stream_id}")
    return {"status": "flushed", "stream_id": stream_id}

@app.get("/api/violations", response_model=List[Dict[str, Any]])
async def get_violations():
    """Get list of recent violations."""
    return list(service.violation_history)

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy", 
        "active_ws_connections": len(service.manager.active_connections),
        "active_streams": len(service.latest_frames),
        "total_violations": len(service.violation_history)
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Streaming Service",
        "status": "running",
        "endpoints": {
            "websocket": "/ws",
            "health": "/api/health",
            "violations": "/api/violations",
            "start_stream": "/api/start-stream",
            "stop_stream": "/api/stop-stream"
        }
    }