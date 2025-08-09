from ultralytics import YOLO
import torch
import logging
import os
from typing import Optional, List, Dict, Union, Any

logger = logging.getLogger(__name__)


class YOLODetector:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model: Optional[YOLO] = None
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.class_names = ['Hand', 'Person', 'Pizza', 'Scooper']  # Expected classes from the model
        self.load_model()

    def load_model(self) -> None:
        """Load YOLO model with proper error handling"""
        try:
            logger.info(f"Loading YOLO model from {self.model_path}")
            logger.info(f"Using device: {self.device}")

            # Check if model file exists
            if not os.path.exists(self.model_path):
                logger.error(f"Model file not found: {self.model_path}")
                logger.info("Downloading default YOLOv8 model as fallback")
                self.model = YOLO('yolov8m.pt')
                self.model.to(self.device)
                return

            # Load the custom trained model
            try:
                self.model = YOLO(self.model_path)
                self.model.to(self.device)
                
                # Verify model has expected classes
                if hasattr(self.model, 'names') and self.model.names is not None:
                    model_classes = self.model.names
                    logger.info(f"Model loaded with classes: {model_classes}")
                    
                    # Check if expected classes are present
                    class_values: Optional[List[str]] = None
                    if isinstance(model_classes, dict):
                        class_values = list(model_classes.values())
                    elif isinstance(model_classes, (list, tuple)):
                        class_values = list(model_classes)
                    else:
                        logger.warning(f"Unexpected model classes type: {type(model_classes)}")
                        class_values = None
                    
                    # Only proceed if we have valid class values
                    if class_values is not None:
                        # Normalize class names for comparison
                        normalized_model_classes = [c.lower() for c in class_values if c is not None]
                        normalized_expected_classes = [c.lower() for c in self.class_names]
                        
                        missing_classes = set(normalized_expected_classes) - set(normalized_model_classes)
                        if missing_classes:
                            logger.warning(f"Model missing expected classes: {missing_classes}")
                            logger.warning(f"Model has classes: {class_values}")
                    else:
                        logger.warning("Could not extract class names from model")
                else:
                    logger.warning("Model does not have class names attribute")
                
                logger.info("Custom model loaded successfully")
                
            except Exception as e:
                logger.error(f"Failed to load custom model: {e}")
                logger.info("Falling back to default YOLOv8 model")
                self.model = YOLO('yolov8m.pt')
                self.model.to(self.device)

        except Exception as e:
            logger.error(f"Critical error loading model: {e}")
            raise

    def detect(self, image: Any, conf_threshold: float = 0.4, iou_threshold: float = 0.5) -> Any:
        """Run detection on image with optimized parameters"""
        if self.model is None:
            raise ValueError("Model not loaded")

        # Run inference with appropriate thresholds
        results = self.model(
            image, 
            conf=conf_threshold,  # Lower confidence threshold for better detection
            iou=iou_threshold,    # IOU threshold for NMS
            device=self.device,
            verbose=False
        )
        
        return results