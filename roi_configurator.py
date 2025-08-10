#!/usr/bin/env python3
"""
File: /roi_configurator.py (root directory)
ROI Configuration Tool for Pizza Store Violation Detection
This script helps you visually set up the ROI for the protein container
"""

import cv2
import json
import sys
import os
from pathlib import Path
from typing import Optional, Tuple

class ROIConfigurator:
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            print(f"Error: Cannot open video {video_path}")
            sys.exit(1)
            
        # Get first frame
        ret, self.frame = self.cap.read()
        if not ret:
            print("Error: Cannot read first frame")
            sys.exit(1)
            
        self.original_frame = self.frame.copy()
        self.height, self.width = self.frame.shape[:2]
        
        # ROI coordinates with proper typing
        self.roi_start: Optional[Tuple[int, int]] = None
        self.roi_end: Optional[Tuple[int, int]] = None
        self.drawing = False
        self.roi_defined = False
        
        print(f"Video dimensions: {self.width}x{self.height}")
        
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for ROI selection"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.roi_start = (x, y)
            self.roi_end = (x, y)
            
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                self.roi_end = (x, y)
                
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.roi_end = (x, y)
            self.roi_defined = True
            
    def draw_roi(self):
        """Draw the ROI on the frame"""
        temp_frame = self.original_frame.copy()
        
        if self.roi_start is not None and self.roi_end is not None:
            # Draw ROI rectangle
            cv2.rectangle(temp_frame, self.roi_start, self.roi_end, (0, 0, 255), 2)
            
            # Draw ROI label
            label = "Protein Container ROI"
            cv2.putText(temp_frame, label, 
                       (self.roi_start[0], self.roi_start[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Show coordinates
            coords_text = f"({self.roi_start[0]}, {self.roi_start[1]}) to ({self.roi_end[0]}, {self.roi_end[1]})"
            cv2.putText(temp_frame, coords_text,
                       (10, self.height - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
        return temp_frame
    
    def run(self):
        """Run the ROI configuration tool"""
        window_name = "ROI Configuration - Draw rectangle around protein container"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.mouse_callback)
        
        print("\n" + "="*60)
        print("ROI CONFIGURATION TOOL")
        print("="*60)
        print("\nInstructions:")
        print("1. Click and drag to draw a rectangle around the PROTEIN CONTAINER")
        print("2. Press 'r' to reset and redraw")
        print("3. Press 's' to save the ROI configuration")
        print("4. Press 'n' to go to next frame")
        print("5. Press 'q' to quit without saving")
        print("\nNOTE: The protein container is typically on the left side")
        print("where workers grab ingredients with/without a scooper")
        print("="*60 + "\n")
        
        while True:
            display_frame = self.draw_roi()
            cv2.imshow(window_name, display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('r'):  # Reset
                self.roi_start = None
                self.roi_end = None
                self.roi_defined = False
                print("ROI reset. Draw again.")
                
            elif key == ord('n'):  # Next frame
                ret, self.frame = self.cap.read()
                if ret:
                    self.original_frame = self.frame.copy()
                    print("Moved to next frame")
                else:
                    print("End of video, restarting...")
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, self.frame = self.cap.read()
                    self.original_frame = self.frame.copy()
                    
            elif key == ord('s'):  # Save
                if self.roi_defined:
                    self.save_roi()
                    break
                else:
                    print("Please define ROI first!")
                    
            elif key == ord('q'):  # Quit
                print("Exiting without saving...")
                break
                
        self.cap.release()
        cv2.destroyAllWindows()
        
    def save_roi(self):
        """Save ROI configuration to JSON file"""
        if not self.roi_defined:
            print("No ROI defined!")
            return
        
        # Check that roi_start and roi_end are not None before accessing
        if self.roi_start is None or self.roi_end is None:
            print("Error: ROI coordinates are not properly defined!")
            return
            
        # Ensure coordinates are in correct order
        x1 = min(self.roi_start[0], self.roi_end[0])
        y1 = min(self.roi_start[1], self.roi_end[1])
        x2 = max(self.roi_start[0], self.roi_end[0])
        y2 = max(self.roi_start[1], self.roi_end[1])
        
        roi_config = {
            "frame_width": self.width,
            "frame_height": self.height,
            "rois": [
                {
                    "id": "roi_1",
                    "name": "Main Protein Container",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "type": "protein_container",
                    "active": True
                }
            ]
        }
        
        # Save to file in root directory
        output_path = "roi_config.json"
        with open(output_path, 'w') as f:
            json.dump(roi_config, f, indent=2)
            
        print("\n" + "="*60)
        print("✅ ROI Configuration Saved!")
        print("="*60)
        print(f"File: {output_path}")
        print(f"ROI Coordinates: ({x1}, {y1}) to ({x2}, {y2})")
        print(f"ROI Size: {x2-x1}x{y2-y1} pixels")
        print("\nThis configuration will be used by the detection system.")
        print("Make sure to rebuild your Docker containers for changes to take effect:")
        print("  docker-compose down")
        print("  docker-compose up --build")
        print("="*60 + "\n")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python roi_configurator.py <video_path>")
        print("Example: python roi_configurator.py 'data/videos/Sah w b3dha ghalt.mp4'")
        sys.exit(1)
        
    video_path = sys.argv[1]
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
        
    configurator = ROIConfigurator(video_path)
    configurator.run()


if __name__ == "__main__":
    main()