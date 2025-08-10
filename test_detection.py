#!/usr/bin/env python3
"""
File: /test_detection.py (root directory)
Test script to verify YOLO model detection
"""

import cv2
import sys
import os
from pathlib import Path
from ultralytics import YOLO
import json
from typing import Dict, Any, Optional

def test_model_on_video(model_path: str, video_path: str, roi_config_path: str = "roi_config.json"):
    """Test the YOLO model on a video"""
    
    print("="*60)
    print("YOLO Model Detection Test")
    print("="*60)
    
    # Load model
    if not os.path.exists(model_path):
        print(f"❌ Model not found: {model_path}")
        return
        
    print(f"Loading model: {model_path}")
    model = YOLO(model_path)
    
    # Print model info - with proper None check
    if hasattr(model, 'names') and model.names is not None:
        print(f"\nModel Classes:")
        # Check if it's a dict or list
        if isinstance(model.names, dict):
            for idx, name in model.names.items():
                print(f"  {idx}: {name}")
        elif isinstance(model.names, (list, tuple)):
            for idx, name in enumerate(model.names):
                print(f"  {idx}: {name}")
        else:
            print(f"  Model names type: {type(model.names)}")
    else:
        print("\n⚠️  Warning: Model does not have class names attribute")
    
    # Load ROI config if exists
    roi: Optional[Dict[str, Any]] = None
    if os.path.exists(roi_config_path):
        try:
            with open(roi_config_path, 'r') as f:
                config = json.load(f)
                if config.get('rois') and len(config['rois']) > 0:
                    roi = config['rois'][0]
                    print(f"\n✅ ROI loaded: {roi['name']}")
                    print(f"  Position: ({roi['x1']}, {roi['y1']}) to ({roi['x2']}, {roi['y2']})")
        except Exception as e:
            print(f"⚠️  Warning: Could not load ROI config: {e}")
    else:
        print(f"\n⚠️  No ROI configuration found at {roi_config_path}")
        print("  Run roi_configurator.py first to set up the ROI")
    
    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Cannot open video: {video_path}")
        return
    
    print(f"\nProcessing video: {video_path}")
    print("Press 'q' to quit, SPACE to pause/resume")
    print("-"*60)
    
    frame_count = 0
    paused = False
    
    # Statistics
    detection_stats: Dict[str, int] = {}
    hands_in_roi = 0
    scoopers_detected = 0
    
    # Get model names safely
    model_names: Optional[Dict[int, str]] = None
    if hasattr(model, 'names') and model.names is not None:
        if isinstance(model.names, dict):
            model_names = model.names
        elif isinstance(model.names, (list, tuple)):
            model_names = {i: name for i, name in enumerate(model.names)}
    
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            # Run detection
            results = model(frame, conf=0.3, verbose=False)
            
            # Process detections
            if results and len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    
                    # Get class name safely
                    if model_names is not None:
                        class_name = model_names.get(cls_id, f"class_{cls_id}")
                    else:
                        class_name = f"class_{cls_id}"
                    
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    # Update statistics
                    if class_name not in detection_stats:
                        detection_stats[class_name] = 0
                    detection_stats[class_name] += 1
                    
                    # Determine color based on class
                    color = (0, 255, 0)  # Green default
                    if class_name.lower() == 'hand':
                        color = (0, 0, 255)  # Red for hand
                        
                        # Check if hand is in ROI
                        if roi is not None:
                            hand_center_x = (x1 + x2) / 2
                            hand_center_y = (y1 + y2) / 2
                            if (roi['x1'] <= hand_center_x <= roi['x2'] and 
                                roi['y1'] <= hand_center_y <= roi['y2']):
                                hands_in_roi += 1
                                color = (0, 165, 255)  # Orange for hand in ROI
                                
                    elif class_name.lower() == 'scooper':
                        color = (255, 0, 0)  # Blue for scooper
                        scoopers_detected += 1
                    elif class_name.lower() == 'pizza':
                        color = (128, 0, 128)  # Purple for pizza
                    elif class_name.lower() == 'person':
                        color = (255, 165, 0)  # Orange for person
                    
                    # Draw bounding box
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    
                    # Draw label
                    label = f"{class_name}: {conf:.2f}"
                    cv2.putText(frame, label, (int(x1), int(y1) - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Draw ROI if configured
            if roi is not None:
                cv2.rectangle(frame, (roi['x1'], roi['y1']), (roi['x2'], roi['y2']), 
                             (255, 0, 0), 2)  # Blue for ROI
                cv2.putText(frame, "ROI: Protein Container", 
                           (roi['x1'], roi['y1'] - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            
            # Draw frame info
            info_text = f"Frame: {frame_count} | Hands in ROI: {hands_in_roi} | Scoopers: {scoopers_detected}"
            cv2.putText(frame, info_text, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Show frame
            cv2.imshow("Detection Test", frame)
        
        # Handle keyboard
        key = cv2.waitKey(1 if not paused else 0) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
            if paused:
                print(f"\nPAUSED at frame {frame_count}")
                print("Current statistics:")
                for class_name, count in detection_stats.items():
                    avg_per_frame = count / frame_count if frame_count > 0 else 0
                    print(f"  {class_name}: {count} total ({avg_per_frame:.2f}/frame)")
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Print final statistics
    print("\n" + "="*60)
    print("DETECTION STATISTICS")
    print("="*60)
    print(f"Total frames processed: {frame_count}")
    
    if detection_stats:
        print(f"\nTotal detections by class:")
        for class_name, count in sorted(detection_stats.items()):
            print(f"  {class_name}: {count}")
        print(f"\nViolation-related statistics:")
        print(f"  Hands detected in ROI: {hands_in_roi}")
        print(f"  Scoopers detected: {scoopers_detected}")
        
        if hands_in_roi > 0 and scoopers_detected == 0:
            print("\n⚠️  WARNING: Hands detected in ROI but no scoopers!")
            print("This suggests potential violations might be present.")
    else:
        print("\n⚠️  No detections found. Possible issues:")
        print("  - Model may not be loaded correctly")
        print("  - Confidence threshold may be too high")
        print("  - Model may not be the fine-tuned version")
    
    print("="*60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_detection.py <video_path> [model_path]")
        print("Example: python test_detection.py 'data/videos/Sah w b3dha ghalt.mp4' models/yolo12m-v2.pt")
        sys.exit(1)
    
    video_path = sys.argv[1]
    model_path = sys.argv[2] if len(sys.argv) > 2 else "models/yolo12m-v2.pt"
    
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        sys.exit(1)
    
    test_model_on_video(model_path, video_path)


if __name__ == "__main__":
    main()