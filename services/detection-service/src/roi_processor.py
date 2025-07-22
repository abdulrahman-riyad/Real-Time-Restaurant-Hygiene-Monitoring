"""
ROI (Region of Interest) processor for managing detection zones
"""

import json
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np
from dataclasses import dataclass
from pathlib import Path

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
        """Load default ROI configuration"""
        # Default protein container area
        default_roi = ROI(
            id="roi_1",
            name="Protein Container",
            x1=200,
            y1=150,
            x2=440,
            y2=350,
            type="protein_container"
        )
        self.add_roi(default_roi)

        logger.info(f"Loaded default ROI: {default_roi.name}")

    def load_from_config(self, config_path: str):
        """Load ROIs from JSON configuration file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            for roi_data in config.get('rois', []):
                roi = ROI(**roi_data)
                self.add_roi(roi)

            logger.info(f"Loaded {len(self.rois)} ROIs from config")

        except Exception as e:
            logger.error(f"Failed to load ROI config: {e}")
            self.load_defaults()

    def save_to_config(self, config_path: str):
        """Save current ROI configuration to file"""
        try:
            config = {
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

    def get_visualization_data(self) -> List[Dict]:
        """Get ROI data formatted for visualization"""
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
                'color': '#3B82F6' if roi.type == 'protein_container' else '#10B981',
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

        return warnings


# Example usage and testing
if __name__ == "__main__":
    # Create ROI processor
    processor = ROIProcessor()

    # Add additional ROI
    new_roi = ROI(
        id="roi_2",
        name="Secondary Container",
        x1=100,
        y1=200,
        x2=300,
        y2=400,
        type="ingredient_container"
    )
    processor.add_roi(new_roi)

    # Test point checking
    test_points = [
        (250, 250),  # In default ROI
        (150, 300),  # In secondary ROI
        (500, 500),  # Outside all ROIs
    ]

    for x, y in test_points:
        rois = processor.check_point_in_rois(x, y)
        if rois:
            print(f"Point ({x}, {y}) is in ROIs: {[roi.name for roi in rois]}")
        else:
            print(f"Point ({x}, {y}) is not in any ROI")

    # Save configuration
    processor.save_to_config("roi_config.json")