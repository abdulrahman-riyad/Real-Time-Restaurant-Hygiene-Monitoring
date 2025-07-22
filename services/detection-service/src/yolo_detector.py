from ultralytics import YOLO
import torch
import logging
import os

logger = logging.getLogger(__name__)


class YOLODetector:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.device = 'cpu'
        self.load_model()

    def load_model(self):
        """Load YOLO model"""
        try:
            logger.info(f"Loading YOLO model from {self.model_path}")

            # Check if model file exists
            if not os.path.exists(self.model_path):
                logger.error(f"Model file not found: {self.model_path}")
                # Use a default YOLO model as fallback
                logger.info("Using default YOLOv8 model")
                self.model = YOLO('yolov8m.pt')
                return

            # Try to load the model
            try:
                self.model = YOLO(self.model_path)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load custom model: {e}")
                logger.info("Falling back to default YOLOv8 model")
                self.model = YOLO('yolov8m.pt')

        except Exception as e:
            logger.error(f"Critical error loading model: {e}")
            raise

    def detect(self, image):
        """Run detection on image"""
        if self.model is None:
            raise ValueError("Model not loaded")

        results = self.model(image)
        return results