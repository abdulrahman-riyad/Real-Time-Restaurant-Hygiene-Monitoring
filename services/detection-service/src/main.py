try:
    import ultralytics_patch
except ImportError:
    pass  # Patch is optional

import pika
import pika.exceptions
import json
import logging
import time
import os
import base64
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, cast

from pika.adapters.blocking_connection import BlockingChannel

# Import your custom modules (these import ultralytics internally)
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
        self.channel: Optional[BlockingChannel] = None
        self.frame_dimensions = None

        # Initialize detection components
        logger.info("Initializing detection components...")
        
        # CRITICAL: Ensure we're using the fine-tuned model
        if not os.path.exists(model_path):
            logger.error(f"❌ CRITICAL: Fine-tuned model not found at {model_path}")
            logger.error("The system REQUIRES the fine-tuned yolo12m-v2.pt model to detect violations correctly!")
            raise FileNotFoundError(f"Required model file not found: {model_path}")
        
        # Initialize YOLO detector with the fine-tuned model
        self.yolo_detector = YOLODetector(model_path=model_path)
        
        # Initialize ROI processor - adjusted for typical pizza store layout
        roi_config_path = "/app/roi_config.json"
        if Path(roi_config_path).exists():
            self.roi_processor = ROIProcessor(config_path=roi_config_path)
            logger.info(f"Loaded ROI configuration from {roi_config_path}")
        else:
            # Use optimized default ROI for protein container (left side of prep area)
            self.roi_processor = ROIProcessor()
            logger.info("Using default ROI configuration optimized for protein container")
        
        # Get the default ROI for violation detection
        active_rois = self.roi_processor.get_active_rois()
        if not active_rois:
            # Create default ROI if none exists - optimized for test videos
            from roi_processor import ROI
            default_roi = ROI(
                id="roi_1",
                name="Protein Container",
                x1=140,  # Left side of prep area
                y1=155,  # Middle-upper area where containers are
                x2=160,  # About 200px wide
                y2=177,  # About 170px tall
                type="protein_container"
            )
            self.roi_processor.add_roi(default_roi)
            active_rois = [default_roi]
            logger.warning("Created default ROI optimized for protein container location")
        
        default_roi = active_rois[0]
        default_roi_coords = {
            'x1': default_roi.x1,
            'y1': default_roi.y1,
            'x2': default_roi.x2,
            'y2': default_roi.y2,
        }
        
        # Initialize enhanced violation detector
        self.violation_detector = ViolationDetector(roi_coords=default_roi_coords)
        logger.info(f"ViolationDetector initialized with ROI: {default_roi.name} at {default_roi_coords}")
        
        # Performance tracking
        self.frames_processed = 0
        self.total_violations_detected = 0
        self.start_time = time.time()
        self.last_stats_time = time.time()
        
        # Track violations per stream for validation
        self.stream_violations = {}
        
        self._connect_rabbitmq()

    def _connect_rabbitmq(self):
        """Establishes a connection to RabbitMQ with retry logic."""
        max_retries = 10
        for i in range(max_retries):
            try:
                self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                ch = cast(BlockingChannel, self.connection.channel())

                ch.queue_declare(queue='video_frames', durable=True)
                ch.queue_declare(queue='detection_results', durable=True)

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
            
            # Initialize stream tracking if needed
            if stream_id not in self.stream_violations:
                self.stream_violations[stream_id] = []
                logger.info(f"New stream started: {stream_id}")
            
            # Decode frame
            img_data = base64.b64decode(frame_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.error("Failed to decode frame")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            
            # Auto-adjust ROIs on first frame if needed
            if self.frame_dimensions is None:
                height, width = frame.shape[:2]
                self.frame_dimensions = (width, height)
                self.roi_processor.auto_adjust_rois(width, height)
                logger.info(f"Frame dimensions set to {width}x{height}, ROIs adjusted")
            
            # Run YOLO detection with optimized parameters for the fine-tuned model
            # These thresholds are specifically tuned for the yolo12m-v2.pt model
            # to detect hands, scoopers, pizzas, and persons accurately
            results = self.yolo_detector.detect(frame, conf_threshold=0.3, iou_threshold=0.4)
            
            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                class_names_dict = results[0].names if hasattr(results[0], 'names') else {}
                
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    # IMPORTANT: Use exact class names from the fine-tuned model
                    # The model was trained with: Hand, Person, Pizza, Scooper
                    class_name = class_names_dict.get(cls_id, "unknown")
                    
                    # Keep original class names from model (capital first letter)
                    # Don't normalize as it might break matching
                    
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    # Keep original class names from model
                    # The fine-tuned model uses: Hand, Person, Pizza, Scooper
                    # Map to lowercase for internal logic consistency
                    class_name_lower = class_name.lower()
                    
                    detection_data = {
                        'class_name': class_name_lower,  # Use lowercase for logic
                        'original_class': class_name,    # Keep original for debugging
                        'confidence': float(box.conf[0]),
                        'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                        'center': {'x': (x1 + x2) / 2, 'y': (y1 + y2) / 2}
                    }
                    detections.append(detection_data)
                
                # Log detection summary for debugging
                if detections:
                    class_counts = {}
                    for d in detections:
                        # Use original class name for display
                        class_name = d.get('original_class', d['class_name'])
                        class_counts[class_name] = class_counts.get(class_name, 0) + 1
                    # Log every 30 frames
                    if self.frames_processed % 30 == 0:
                        logger.debug(f"Frame {frame_id}: Detected {class_counts}")
            
            # Run enhanced violation detection
            violations = self.violation_detector.detect_violations(detections, frame_id, stream_id)
            
            if violations:
                for v in violations:
                    self.total_violations_detected += 1
                    self.stream_violations[stream_id].append(v)
                    logger.warning(f"🚨 VIOLATION #{self.total_violations_detected} in stream {stream_id}: {v['message']}")
                    
                    # Log stream-specific violation count for validation
                    stream_violation_count = len(self.stream_violations[stream_id])
                    logger.info(f"Stream {stream_id} total violations: {stream_violation_count}")
            
            # Prepare result message
            result_message = {
                'stream_id': stream_id,
                'frame_id': frame_id,
                'timestamp': frame_data.get('timestamp'),
                'detections': detections,
                'violations': violations,
                'rois': self.roi_processor.get_visualization_data(),
                'processed_at': time.time(),
                'stats': {
                    **self.violation_detector.get_statistics(),
                    'stream_violations': len(self.stream_violations.get(stream_id, []))
                }
            }
            
            # Ensure channel is available before publishing
            self._ensure_connection()
            if self.channel:
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
                logger.info(f"📊 Performance: {self.frames_processed} frames, "
                          f"FPS: {fps:.2f}, "
                          f"Total violations: {self.total_violations_detected}")
                
                # Log per-stream violations for validation
                for sid, vlist in self.stream_violations.items():
                    if vlist:
                        logger.info(f"  Stream {sid}: {len(vlist)} violations")
                
                self.last_stats_time = current_time
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Critical error processing frame: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        """Starts the service by consuming messages from the queue."""
        logger.info("Starting detection service and waiting for frames...")
        logger.info("=" * 60)
        logger.info("VIOLATION DETECTION SYSTEM READY")
        logger.info("Expected violations in test videos:")
        logger.info("  - 'Sah w b3dha ghalt.mp4': 1 violation")
        logger.info("  - 'Sah w b3dha ghalt (2).mp4': 2 violations")
        logger.info("  - 'Sah w b3dha ghalt (3).mp4': 1 violation")
        logger.info("=" * 60)
        
        self._ensure_connection()
        
        if not self.channel:
            raise RuntimeError("Failed to establish channel connection")
        
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
            logger.info("=" * 60)
            logger.info("FINAL STATISTICS")
            logger.info(f"Service ran for {elapsed:.2f} seconds")
            logger.info(f"Total frames processed: {self.frames_processed}")
            logger.info(f"Total violations detected: {self.total_violations_detected}")
            
            # Log per-stream final counts
            for stream_id, violations in self.stream_violations.items():
                if violations:
                    logger.info(f"Stream {stream_id}: {len(violations)} violations")
            
            logger.info("=" * 60)
            
            if self.channel and not self.channel.is_closed:
                self.channel.stop_consuming()
            if self.connection and not self.connection.is_closed:
                self.connection.close()


def main():
    """Entry point for the service."""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:admin@rabbitmq:5672/')
    model_path = os.getenv('MODEL_PATH', '/app/models/yolo12m-v2.pt')
    
    # CRITICAL: Verify model file exists
    if not os.path.exists(model_path):
        logger.error("=" * 60)
        logger.error("❌ CRITICAL ERROR: Fine-tuned model not found!")
        logger.error(f"Expected location: {model_path}")
        logger.error("The system REQUIRES the fine-tuned yolo12m-v2.pt model")
        logger.error("Please ensure the model file is in the models/ directory")
        logger.error("=" * 60)
        return 1
    
    # Verify model size
    file_size = os.path.getsize(model_path)
    logger.info(f"Model file found: {model_path} (size: {file_size / 1024 / 1024:.2f} MB)")
    
    if file_size < 10_000_000:  # Less than 10MB is suspicious
        logger.error("Model file seems too small, might be corrupted!")
        return 1
    
    # Check for ROI configuration
    roi_config_path = "/app/roi_config.json"
    if not Path(roi_config_path).exists():
        logger.info("No custom ROI configuration found. Using optimized defaults for protein container.")
    
    try:
        service = DetectionService(rabbitmq_url, model_path)
        service.run()
    except Exception as e:
        logger.error(f"Failed to start detection service: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())