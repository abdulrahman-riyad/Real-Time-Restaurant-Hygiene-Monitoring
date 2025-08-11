"""
File: /services/detection-service/src/yolo_detector.py
YOLO detector module for the Pizza Store Violation Detection System
"""

# Import compatibility module first
try:
    from c3k2_compat import inject_c3k2_module
    inject_c3k2_module()
except ImportError:
    pass  # Compatibility module is optional

from ultralytics import YOLO
import torch
import logging
import os
from typing import Optional, List, Dict, Union, Any
import sys

logger = logging.getLogger(__name__)


class YOLODetector:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model: Optional[YOLO] = None
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        # These are the expected classes from the fine-tuned model
        self.expected_classes = ['Hand', 'Person', 'Pizza', 'Scooper']
        self.load_model()

    def load_model(self) -> None:
        """Load YOLO model with proper error handling"""
        try:
            logger.info(f"=" * 60)
            logger.info(f"YOLO Model Loading Process Starting")
            logger.info(f"=" * 60)
            logger.info(f"Model path: {self.model_path}")
            logger.info(f"Using device: {self.device}")

            # Check if model file exists
            if not os.path.exists(self.model_path):
                logger.error(f"❌ Model file not found: {self.model_path}")
                logger.error("The fine-tuned model is REQUIRED for proper violation detection!")
                logger.error("Please ensure 'yolo12m-v2.pt' is in the models/ directory")
                
                # List contents of models directory for debugging
                models_dir = os.path.dirname(self.model_path)
                if os.path.exists(models_dir):
                    logger.info(f"Contents of {models_dir}:")
                    for file in os.listdir(models_dir):
                        logger.info(f"  - {file}")
                else:
                    logger.error(f"Models directory does not exist: {models_dir}")
                
                # Exit since we NEED the fine-tuned model
                logger.critical("Cannot proceed without fine-tuned model. Exiting...")
                sys.exit(1)

            # Check file size
            file_size = os.path.getsize(self.model_path)
            logger.info(f"Model file size: {file_size / 1024 / 1024:.2f} MB")
            
            if file_size < 10_000_000:  # Less than 10MB is suspicious for YOLO model
                logger.warning(f"⚠️  Model file might be corrupted (only {file_size / 1024 / 1024:.2f} MB)")

            # Load the custom trained model
            logger.info("Loading fine-tuned YOLO model...")
            self.model = YOLO(self.model_path)
            self.model.to(self.device)
            
            # Verify model has expected classes
            if hasattr(self.model, 'names') and self.model.names is not None:
                model_classes = self.model.names
                logger.info(f"✅ Model loaded successfully!")
                logger.info(f"Model class mapping: {model_classes}")
                
                # Check class names format
                if isinstance(model_classes, dict):
                    class_values = list(model_classes.values())
                    logger.info(f"Model classes (values): {class_values}")
                    
                    # Verify expected classes are present
                    for expected_class in self.expected_classes:
                        found = False
                        for idx, class_name in model_classes.items():
                            if class_name.lower() == expected_class.lower():
                                found = True
                                logger.info(f"  ✓ Found '{expected_class}' as '{class_name}' (index {idx})")
                                break
                        if not found:
                            logger.warning(f"  ✗ Expected class '{expected_class}' not found in model")
                elif isinstance(model_classes, (list, tuple)):
                    logger.info(f"Model classes (list): {list(model_classes)}")
                else:
                    logger.warning(f"Unexpected model classes type: {type(model_classes)}")
                
                # Print the exact class names the model uses
                logger.info("=" * 60)
                logger.info("IMPORTANT: Model uses these exact class names:")
                if isinstance(model_classes, dict):
                    for idx, name in model_classes.items():
                        logger.info(f"  Class {idx}: '{name}'")
                logger.info("=" * 60)
                
            else:
                logger.error("❌ Model does not have class names attribute")
                logger.error("This might not be the correct fine-tuned model!")
                sys.exit(1)
            
            # Test inference to make sure model works
            logger.info("Testing model inference...")
            test_image = torch.randn(640, 640, 3).numpy()
            test_results = self.model(test_image, verbose=False)
            logger.info("✅ Model inference test passed")
            
            logger.info(f"=" * 60)
            logger.info(f"YOLO Model Successfully Loaded and Verified!")
            logger.info(f"=" * 60)
                
        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR loading model: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            
            # Check for specific error types
            if "C3k2" in str(e):
                logger.error("=" * 60)
                logger.error("MODEL VERSION COMPATIBILITY ISSUE DETECTED")
                logger.error("=" * 60)
                logger.error("The model requires the C3k2 module which is not in your ultralytics version.")
                logger.error("")
                logger.error("SOLUTION:")
                logger.error("1. Update requirements.txt to use: ultralytics>=8.2.0")
                logger.error("2. Rebuild the detection service:")
                logger.error("   docker-compose build --no-cache detection-service")
                logger.error("3. Restart the services:")
                logger.error("   docker-compose up")
                logger.error("=" * 60)
            else:
                logger.error(f"This likely means the model file is incompatible or corrupted")
                logger.error("Please ensure you have the correct 'yolo12m-v2.pt' file")
            
            import traceback
            logger.error(traceback.format_exc())
            sys.exit(1)

    def detect(self, image: Any, conf_threshold: float = 0.4, iou_threshold: float = 0.5) -> Any:
        """Run detection on image with optimized parameters"""
        if self.model is None:
            raise ValueError("Model not loaded")

        # Run inference with appropriate thresholds
        results = self.model(
            image, 
            conf=conf_threshold,  # Confidence threshold
            iou=iou_threshold,    # IOU threshold for NMS
            device=self.device,
            verbose=False
        )
        
        # Log detection summary for debugging
        if results and len(results) > 0:
            if results[0].boxes is not None:
                num_detections = len(results[0].boxes)
                if num_detections > 0:
                    logger.debug(f"Detected {num_detections} objects in frame")
                    
                    # Log what was detected
                    if hasattr(results[0], 'names'):
                        class_counts = {}
                        for box in results[0].boxes:
                            cls_id = int(box.cls[0])
                            class_name = results[0].names.get(cls_id, f"class_{cls_id}")
                            class_counts[class_name] = class_counts.get(class_name, 0) + 1
                        if class_counts:
                            logger.debug(f"Detection summary: {class_counts}")
        
        return results