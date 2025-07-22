import pika
import json
import logging
import time
import os
import base64
import numpy as np
import cv2

# Import your custom, intelligent modules
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
        self.connection = None
        self.channel = None

        # --- Initialize the REAL detection components ---
        logger.info("Initializing real detection components...")
        self.yolo_detector = YOLODetector(model_path=model_path)
        self.roi_processor = ROIProcessor()  # This loads your default ROI

        # Get the default ROI to initialize the violation detector
        # In a more advanced system, this could be updated dynamically
        active_rois = self.roi_processor.get_active_rois()
        if not active_rois:
            raise ValueError("No active ROIs found in ROIProcessor. Cannot start ViolationDetector.")

        # We'll use the first active ROI for violation detection logic
        default_roi_coords = active_rois[0].to_dict()
        self.violation_detector = ViolationDetector(roi_coords={
            'x1': default_roi_coords['x1'],
            'y1': default_roi_coords['y1'],
            'x2': default_roi_coords['x2'],
            'y2': default_roi_coords['y2'],
        })
        logger.info(f"ViolationDetector initialized with ROI: {default_roi_coords['name']}")

        self._connect_rabbitmq()

    def _connect_rabbitmq(self):
        """Establishes a connection to RabbitMQ with retry logic."""
        max_retries = 10
        for i in range(max_retries):
            try:
                self.connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
                self.channel = self.connection.channel()

                # Ensure both queues exist
                self.channel.queue_declare(queue='video_frames', durable=True)
                self.channel.queue_declare(queue='detection_results', durable=True)

                logger.info("Successfully connected to RabbitMQ.")
                return
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection failed (attempt {i + 1}/{max_retries}): {e}")
                time.sleep(5)
        raise Exception("Failed to connect to RabbitMQ after multiple retries.")

    def process_frame(self, ch, method, properties, body):
        """
        This is the core callback function that gets executed for each frame.
        """
        try:
            frame_data = json.loads(body)
            stream_id = frame_data.get('stream_id')
            frame_id = frame_data.get('frame_id')
            frame_b64 = frame_data.get('frame_data')

            if not all([stream_id, frame_id, frame_b64]):
                logger.warning("Received incomplete frame data. Discarding.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            img_data = base64.b64decode(frame_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            results = self.yolo_detector.model.predict(frame, conf=0.5, verbose=False)

            detections = []
            if results[0].boxes is not None:
                # Get the class names dictionary from the model.
                # It's safer to get it on every prediction in case the model changes.
                class_names_dict = results[0].names
                
                for box in results[0].boxes:
                    # Ensure cls_id is a valid integer
                    cls_id = int(box.cls[0])
                    
                    # Get the class name. If the ID is invalid for some reason,
                    # default to an "unknown" class name.
                    class_name = class_names_dict.get(cls_id, "unknown")
                    
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    detection_data = {
                        'class_name': class_name,
                        'confidence': float(box.conf[0]),
                        'bbox': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                        'center': {'x': (x1 + x2) / 2, 'y': (y1 + y2) / 2}
                    }
                    detections.append(detection_data)
                
                # Add a log to see what we are detecting
                if detections:
                    detected_classes = [d['class_name'] for d in detections]
                    logger.info(f"Frame {frame_id}: Detected {len(detections)} objects: {detected_classes}")

            violations = self.violation_detector.detect_violations(detections, frame_id)
            if violations:
                logger.warning(f"VIOLATION DETECTED in frame {frame_id} from stream {stream_id}")

            result_message = {
                'stream_id': stream_id,
                'frame_id': frame_id,
                'timestamp': frame_data.get('timestamp'),
                'detections': detections,
                'violations': violations,
                'rois': self.roi_processor.get_visualization_data(),
                'processed_at': time.time()
            }

            self.channel.basic_publish(
                exchange='',
                routing_key='detection_results',
                body=json.dumps(result_message),
                properties=pika.BasicProperties(delivery_mode=2)
            )

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Critical error processing frame: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        """Starts the service by consuming messages from the queue."""
        logger.info("Starting detection service and waiting for frames...")
        # Set Quality of Service: only pre-fetch 1 message at a time
        # This prevents the service from hoarding frames if processing is slow
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
            self.channel.stop_consuming()
            self.connection.close()


def main():
    """Entry point for the service."""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:admin@rabbitmq:5672/')
    model_path = os.getenv('MODEL_PATH', '/app/models/yolo12m-v2.pt')

    # Ensure the model file exists before starting
    if not os.path.exists(model_path):
        logger.error(f"FATAL: Model file not found at {model_path}. Service cannot start.")
        return

    service = DetectionService(rabbitmq_url, model_path)
    service.run()


if __name__ == "__main__":
    main()