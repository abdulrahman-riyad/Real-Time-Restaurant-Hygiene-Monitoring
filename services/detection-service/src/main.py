import pika
import pika.exceptions  # Explicit import for Pylance
import json
import logging
import time
import os
import base64
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, cast

# Import the concrete BlockingChannel type for correct type hints
from pika.adapters.blocking_connection import BlockingChannel

# Import your custom modules
from yolo_detector import YOLODetector
from violation_logic import ViolationDetector
from roi_processor import ROIProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DetectionService:
    """The main service class that connects all detection components."""

    def __init__(self, rabbitmq_url: str, model_path: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection: Optional[pika.BlockingConnection] = None
        # Use BlockingChannel type (not pika.channel.Channel which Pylance can't resolve)
        self.channel: Optional[BlockingChannel] = None
        self.frame_dimensions = None  # Will be set from first frame

        # Initialize detection components
        logger.info("Initializing detection components...")
        
        # Initialize YOLO detector
        self.yolo_detector = YOLODetector(model_path=model_path)
        
        # Initialize ROI processor
        roi_config_path = "/app/roi_config.json"
        if Path(roi_config_path).exists():
            self.roi_processor = ROIProcessor(config_path=roi_config_path)
            logger.info(f"Loaded ROI configuration from {roi_config_path}")
        else:
            self.roi_processor = ROIProcessor()
            logger.info("Using default ROI configuration")
        
        # Get the default ROI to initialize the violation detector
        active_rois = self.roi_processor.get_active_rois()
        if not active_rois:
            raise ValueError("No active ROIs found in ROIProcessor. Cannot start ViolationDetector.")
        
        # Use the first active ROI for violation detection
        default_roi = active_rois[0]
        default_roi_coords = {
            'x1': default_roi.x1,
            'y1': default_roi.y1,
            'x2': default_roi.x2,
            'y2': default_roi.y2,
        }
        self.violation_detector = ViolationDetector(roi_coords=default_roi_coords)
        logger.info(f"ViolationDetector initialized with ROI: {default_roi.name} at {default_roi_coords}")
        
        # Performance tracking
        self.frames_processed = 0
        self.start_time = time.time()
        self.last_stats_time = time.time()
        
        self._connect_rabbitmq()

    def _connect_rabbitmq(self):
        """Establishes a connection to RabbitMQ with retry logic."""
        max_retries = 10
        for i in range(max_retries):
            try:
                self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                # Cast the returned channel to BlockingChannel so type checker knows it's not None
                ch = cast(BlockingChannel, self.connection.channel())

                # Ensure both queues exist (ch is a concrete BlockingChannel)
                ch.queue_declare(queue='video_frames', durable=True)
                ch.queue_declare(queue='detection_results', durable=True)

                # save channel to instance after successful declarations
                self.channel = ch
                
                logger.info("Successfully connected to RabbitMQ.")
                return
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection failed (attempt {i + 1}/{max_retries}): {e}")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error connecting to RabbitMQ: {e}")
                time.sleep(5)
        raise Exception("Failed to connect to RabbitMQ after multiple retries.")

    def _ensure_connection(self):
        """Ensure connection and channel are available."""
        if self.connection is None or self.connection.is_closed:
            self._connect_rabbitmq()
        if self.channel is None or self.channel.is_closed:
            if self.connection and not self.connection.is_closed:
                # cast again so Pylance knows this is a BlockingChannel
                self.channel = cast(BlockingChannel, self.connection.channel())
            else:
                self._connect_rabbitmq()

    def process_frame(self, ch: BlockingChannel, method, properties, body):
        """Core callback function that processes each frame."""
        try:
            frame_data = json.loads(body)
            stream_id = frame_data.get('stream_id')
            frame_id = frame_data.get('frame_id')
            frame_b64 = frame_data.get('frame_data')
            
            if not all([stream_id, frame_id, frame_b64]):
                logger.warning("Received incomplete frame data. Discarding.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            
            # Decode frame
            img_data = base64.b64decode(frame_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.error("Failed to decode frame")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            
            # Auto-adjust ROIs on first frame
            if self.frame_dimensions is None:
                height, width = frame.shape[:2]
                self.frame_dimensions = (width, height)
                self.roi_processor.auto_adjust_rois(width, height)
                logger.info(f"Frame dimensions set to {width}x{height}, ROIs adjusted")
            
            # Run YOLO detection with optimized parameters
            results = self.yolo_detector.detect(frame, conf_threshold=0.35, iou_threshold=0.45)
            
            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                class_names_dict = results[0].names if hasattr(results[0], 'names') else {}
                
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    class_name = class_names_dict.get(cls_id, "unknown")
                    
                    # Normalize class names for consistency
                    class_name_normalized = class_name.capitalize()
                    
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    detection_data = {
                        'class_name': class_name_normalized,
                        'confidence': float(box.conf[0]),
                        'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                        'center': {'x': (x1 + x2) / 2, 'y': (y1 + y2) / 2}
                    }
                    detections.append(detection_data)
                
                # Log detection summary
                if detections:
                    class_counts = {}
                    for d in detections:
                        class_name = d['class_name']
                        class_counts[class_name] = class_counts.get(class_name, 0) + 1
                    logger.debug(f"Frame {frame_id}: Detected {class_counts}")
            
            # Run violation detection
            violations = self.violation_detector.detect_violations(detections, frame_id)
            
            if violations:
                logger.warning(f"VIOLATION DETECTED in frame {frame_id} from stream {stream_id}: {violations[0]['message']}")
            
            # Prepare result message
            result_message = {
                'stream_id': stream_id,
                'frame_id': frame_id,
                'timestamp': frame_data.get('timestamp'),
                'detections': detections,
                'violations': violations,
                'rois': self.roi_processor.get_visualization_data(),
                'processed_at': time.time(),
                'stats': self.violation_detector.get_statistics()
            }
            
            # Ensure channel is available before publishing
            self._ensure_connection()
            if self.channel:
                # Publish results
                self.channel.basic_publish(
                    exchange='',
                    routing_key='detection_results',
                    body=json.dumps(result_message),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
            
            # Update performance metrics
            self.frames_processed += 1
            current_time = time.time()
            if current_time - self.last_stats_time >= 10:  # Log stats every 10 seconds
                elapsed = current_time - self.start_time
                fps = self.frames_processed / elapsed if elapsed > 0 else 0
                logger.info(f"Performance: {self.frames_processed} frames processed, "
                          f"Average FPS: {fps:.2f}, "
                          f"Total violations: {len(self.violation_detector.confirmed_violations)}")
                self.last_stats_time = current_time
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Critical error processing frame: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        """Starts the service by consuming messages from the queue."""
        logger.info("Starting detection service and waiting for frames...")
        
        # Ensure connection is established
        self._ensure_connection()
        
        if not self.channel:
            raise RuntimeError("Failed to establish channel connection")
        
        # Set Quality of Service: only pre-fetch 1 message at a time
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue='video_frames',
            on_message_callback=self.process_frame,
            auto_ack=False
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Stopping detection service.")
            
            # Log final statistics
            elapsed = time.time() - self.start_time
            logger.info(f"Service ran for {elapsed:.2f} seconds")
            logger.info(f"Total frames processed: {self.frames_processed}")
            logger.info(f"Total violations detected: {len(self.violation_detector.confirmed_violations)}")
            
            if self.channel and not self.channel.is_closed:
                self.channel.stop_consuming()
            if self.connection and not self.connection.is_closed:
                self.connection.close()


def check_model_file(model_path: str) -> bool:
    """Check if model file exists and provide helpful messages."""
    if not os.path.exists(model_path):
        logger.error(f"Model file not found at {model_path}")
        logger.info("Please ensure the YOLO model file is placed in the /models directory")
        logger.info("You can download it from the provided link or use the default YOLOv8 model")
        return False
    
    # Check file size to ensure it's not corrupted
    file_size = os.path.getsize(model_path)
    if file_size < 1000000:  # Less than 1MB probably means corrupted
        logger.error(f"Model file seems corrupted (size: {file_size} bytes)")
        return False
    
    logger.info(f"Model file found: {model_path} (size: {file_size / 1024 / 1024:.2f} MB)")
    return True


def main():
    """Entry point for the service."""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:admin@rabbitmq:5672/')
    model_path = os.getenv('MODEL_PATH', '/app/models/yolo12m-v2.pt')
    
    # Check for model file
    if not check_model_file(model_path):
        logger.warning("Custom model not available. Service will use default YOLOv8 model.")
        # The YOLODetector will handle the fallback
    
    # Optional: Check for ROI configuration
    roi_config_path = "/app/roi_config.json"
    if not Path(roi_config_path).exists():
        logger.info("No custom ROI configuration found. Using defaults.")
        logger.info("To customize ROIs, create a roi_config.json file in the project root.")
    
    try:
        service = DetectionService(rabbitmq_url, model_path)
        service.run()
    except Exception as e:
        logger.error(f"Failed to start detection service: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())