"""
ROI (Region of Interest) processor for managing detection zones
"""

import json
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ROI:
    """Region of Interest data class"""
    id: str
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    active: bool = True
    type: str = "protein_container"

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within this ROI"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def get_center(self) -> Tuple[float, float]:
        """Get center point of ROI"""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def get_area(self) -> float:
        """Calculate area of ROI"""
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'x1': self.x1,
            'y1': self.y1,
            'x2': self.x2,
            'y2': self.y2,
            'active': self.active,
            'type': self.type
        }


class ROIProcessor:
    """Manages multiple ROIs for violation detection"""

    def __init__(self, config_path: Optional[str] = None):
        self.rois: Dict[str, ROI] = {}
        self.config_path = config_path

        # Load ROIs from config or use defaults
        if config_path and Path(config_path).exists():
            self.load_from_config(config_path)
        else:
            self.load_defaults()

    def load_defaults(self):
        """Load default ROI configuration based on typical pizza store layout"""
        # Default protein container area - adjusted for 640x480 video
        # This is typically on the left side of the preparation area
        default_roi = ROI(
            id="roi_1",
            name="Protein Container",
            x1=120,  # Adjusted for better positioning
            y1=180,  # Middle-left area
            x2=280,  # About 160px wide
            y2=320,  # About 140px tall
            type="protein_container"
        )
        self.add_roi(default_roi)
        
        # Optional: Add secondary ingredient container
        # Uncomment if needed for multi-container tracking
        """
        secondary_roi = ROI(
            id="roi_2",
            name="Vegetable Container",
            x1=360,
            y1=180,
            x2=520,
            y2=320,
            type="vegetable_container"
        )
        self.add_roi(secondary_roi)
        """

        logger.info(f"Loaded default ROI: {default_roi.name} at ({default_roi.x1}, {default_roi.y1}) to ({default_roi.x2}, {default_roi.y2})")

    def load_from_config(self, config_path: str):
        """Load ROIs from JSON configuration file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Check if config has frame dimensions for scaling
            frame_width = config.get('frame_width', 640)
            frame_height = config.get('frame_height', 480)
            
            for roi_data in config.get('rois', []):
                # Scale ROI coordinates if they're normalized (0-1 range)
                if all(0 <= roi_data.get(coord, 0) <= 1 for coord in ['x1', 'y1', 'x2', 'y2']):
                    roi_data['x1'] *= frame_width
                    roi_data['x2'] *= frame_width
                    roi_data['y1'] *= frame_height
                    roi_data['y2'] *= frame_height
                
                roi = ROI(**roi_data)
                self.add_roi(roi)

            logger.info(f"Loaded {len(self.rois)} ROIs from config")

        except Exception as e:
            logger.error(f"Failed to load ROI config: {e}")
            self.load_defaults()

    def save_to_config(self, config_path: str, frame_width: int = 640, frame_height: int = 480):
        """Save current ROI configuration to file"""
        try:
            config = {
                'frame_width': frame_width,
                'frame_height': frame_height,
                'rois': [roi.to_dict() for roi in self.rois.values()]
            }

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Saved ROI config to: {config_path}")

        except Exception as e:
            logger.error(f"Failed to save ROI config: {e}")

    def add_roi(self, roi: ROI):
        """Add a new ROI"""
        self.rois[roi.id] = roi
        logger.info(f"Added ROI: {roi.id} - {roi.name}")

    def remove_roi(self, roi_id: str):
        """Remove an ROI"""
        if roi_id in self.rois:
            del self.rois[roi_id]
            logger.info(f"Removed ROI: {roi_id}")

    def update_roi(self, roi_id: str, **kwargs):
        """Update ROI properties"""
        if roi_id in self.rois:
            roi = self.rois[roi_id]
            for key, value in kwargs.items():
                if hasattr(roi, key):
                    setattr(roi, key, value)
            logger.info(f"Updated ROI: {roi_id}")

    def get_roi(self, roi_id: str) -> Optional[ROI]:
        """Get ROI by ID"""
        return self.rois.get(roi_id)

    def get_active_rois(self) -> List[ROI]:
        """Get all active ROIs"""
        return [roi for roi in self.rois.values() if roi.active]

    def check_point_in_rois(self, x: float, y: float) -> List[ROI]:
        """Check which ROIs contain a given point"""
        containing_rois = []
        for roi in self.get_active_rois():
            if roi.contains_point(x, y):
                containing_rois.append(roi)
        return containing_rois

    def check_object_in_rois(self, bbox: Dict[str, float]) -> List[ROI]:
        """Check which ROIs contain an object's center point"""
        center_x = (bbox['x1'] + bbox['x2']) / 2
        center_y = (bbox['y1'] + bbox['y2']) / 2
        return self.check_point_in_rois(center_x, center_y)

    def get_roi_overlap(self, bbox: Dict[str, float], roi: ROI) -> float:
        """Calculate overlap percentage between bounding box and ROI"""
        # Calculate intersection
        x1 = max(bbox['x1'], roi.x1)
        y1 = max(bbox['y1'], roi.y1)
        x2 = min(bbox['x2'], roi.x2)
        y2 = min(bbox['y2'], roi.y2)

        if x2 < x1 or y2 < y1:
            return 0.0

        intersection_area = (x2 - x1) * (y2 - y1)
        bbox_area = (bbox['x2'] - bbox['x1']) * (bbox['y2'] - bbox['y1'])

        return intersection_area / bbox_area if bbox_area > 0 else 0.0

    def scale_rois(self, scale_x: float, scale_y: float):
        """Scale all ROIs by given factors"""
        for roi in self.rois.values():
            roi.x1 *= scale_x
            roi.x2 *= scale_x
            roi.y1 *= scale_y
            roi.y2 *= scale_y

    def auto_adjust_rois(self, frame_width: int, frame_height: int):
        """Auto-adjust ROIs based on frame dimensions"""
        # If frame is different from expected 640x480, scale ROIs
        expected_width = 640
        expected_height = 480
        
        if frame_width != expected_width or frame_height != expected_height:
            scale_x = frame_width / expected_width
            scale_y = frame_height / expected_height
            self.scale_rois(scale_x, scale_y)
            logger.info(f"Auto-adjusted ROIs for frame size {frame_width}x{frame_height}")

    def get_visualization_data(self) -> List[Dict]:
        """Get ROI data formatted for visualization"""
        colors = {
            'protein_container': '#3B82F6',  # Blue
            'vegetable_container': '#10B981',  # Green
            'cheese_container': '#F59E0B',  # Yellow
            'sauce_container': '#EF4444'  # Red
        }
        
        return [
            {
                'id': roi.id,
                'name': roi.name,
                'coords': {
                    'x1': roi.x1,
                    'y1': roi.y1,
                    'x2': roi.x2,
                    'y2': roi.y2
                },
                'color': colors.get(roi.type, '#6B7280'),  # Default gray
                'active': roi.active
            }
            for roi in self.rois.values()
        ]

    def validate_roi_placement(self, frame_width: int, frame_height: int) -> List[str]:
        """Validate that ROIs are within frame boundaries"""
        warnings = []

        for roi in self.rois.values():
            if roi.x1 < 0 or roi.y1 < 0:
                warnings.append(f"ROI {roi.id} has negative coordinates")

            if roi.x2 > frame_width or roi.y2 > frame_height:
                warnings.append(f"ROI {roi.id} extends beyond frame boundaries")

            if roi.x1 >= roi.x2 or roi.y1 >= roi.y2:
                warnings.append(f"ROI {roi.id} has invalid dimensions")

            # Check if ROI is too small
            min_size = 50  # minimum 50x50 pixels
            if (roi.x2 - roi.x1) < min_size or (roi.y2 - roi.y1) < min_size:
                warnings.append(f"ROI {roi.id} is too small (< {min_size}x{min_size} pixels)")

        return warnings

    def suggest_roi_placement(self, detections: List[Dict], frame_count: int = 100) -> Dict[str, Tuple[float, float, float, float]]:
        """Suggest ROI placement based on detected container patterns"""
        # This method can analyze detection patterns to suggest optimal ROI placement
        # Useful for initial setup or calibration
        container_candidates = defaultdict(list)
        
        # Analyze where hands frequently appear (potential container locations)
        for detection in detections:
            if detection.get('class_name', '').lower() == 'hand':
                center = detection['center']
                # Group nearby hand detections
                grid_x = int(center['x'] / 100)
                grid_y = int(center['y'] / 100)
                container_candidates[(grid_x, grid_y)].append(center)
        
        # Find most frequent hand interaction areas
        suggestions = {}
        for (grid_x, grid_y), positions in container_candidates.items():
            if len(positions) > frame_count * 0.1:  # At least 10% of frames
                # Calculate bounding box for this area
                xs = [p['x'] for p in positions]
                ys = [p['y'] for p in positions]
                suggestions[f"suggested_roi_{grid_x}_{grid_y}"] = (
                    min(xs) - 30, min(ys) - 30,
                    max(xs) + 30, max(ys) + 30
                )
        
        return suggestions


# Example usage and testing
if __name__ == "__main__":
    # Create ROI processor
    processor = ROIProcessor()

    # Test with custom configuration
    custom_config = {
        'frame_width': 640,
        'frame_height': 480,
        'rois': [
            {
                'id': 'roi_1',
                'name': 'Main Protein Container',
                'x1': 100,
                'y1': 150,
                'x2': 300,
                'y2': 350,
                'type': 'protein_container'
            }
        ]
    }
    
    # Save and load config
    processor.save_to_config('roi_config.json')
    
    # Validate ROI placement
    warnings = processor.validate_roi_placement(640, 480)
    if warnings:
        print("Validation warnings:", warnings)
    
    # Get visualization data
    viz_data = processor.get_visualization_data()
    print("Visualization data:", viz_data)