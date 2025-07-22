import time
import logging
from collections import defaultdict
from typing import List, Dict, Any

# Configure logging to see outputs in the Docker logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ViolationDetector:
    """
    Detects scooper violations based on a simpler, time-based heuristic.
    A violation is triggered if a hand lingers in the ROI without a scooper.
    """
    def __init__(self, roi_coords: Dict[str, float]):
        self.roi_coords = roi_coords
        
        # This dictionary will track hands currently inside the ROI.
        # Format: {hand_id: entry_timestamp}
        self.hands_in_roi_since = defaultdict(float)
        
        # A hand must be inside the ROI for this duration (in seconds)
        # to be considered "picking" rather than just passing through.
        self.PICKING_TIME_THRESHOLD = 0.5
        
        # A cooldown (in seconds) to prevent spamming alerts for a single, continuous violation.
        self.VIOLATION_COOLDOWN = 3.0
        self.last_violation_times = defaultdict(float)

    def _get_hand_id(self, hand: Dict[str, Any]) -> str:
        """Creates a simple, position-based ID for a hand for frame-to-frame tracking."""
        x, y = int(hand['center']['x'] / 50), int(hand['center']['y'] / 50)
        return f"hand_{x}_{y}"

    def _is_in_roi(self, center: Dict[str, float]) -> bool:
        """Checks if a point (like the center of a hand) is within the ROI."""
        return (self.roi_coords['x1'] <= center['x'] <= self.roi_coords['x2'] and
                self.roi_coords['y1'] <= center['y'] <= self.roi_coords['y2'])

    def detect_violations(self, detections: List[Dict[str, Any]], frame_id: str) -> List[Dict[str, Any]]:
        """
        The main detection logic.
        """
        violations = []
        hands = [d for d in detections if d.get('class_name') and 'hand' in d['class_name'].lower()]
        scoopers = [d for d in detections if d.get('class_name') and 'scooper' in d['class_name'].lower()]
        
        current_time = time.time()
                
        # Keep track of which hands from our tracker are still present in the current frame
        current_frame_hand_ids = set()

        for hand in hands:
            hand_id = self._get_hand_id(hand)
            current_frame_hand_ids.add(hand_id)

            if self._is_in_roi(hand['center']):
                # If this is the first time we see this hand in the ROI, record its entry time.
                if hand_id not in self.hands_in_roi_since:
                    self.hands_in_roi_since[hand_id] = current_time
                    logger.info(f"Hand '{hand_id}' entered ROI.")

                # Calculate how long the hand has been inside the ROI.
                time_in_roi = current_time - self.hands_in_roi_since[hand_id]
                
                # Check if the hand is in a cooldown period from a previous violation.
                in_cooldown = (current_time - self.last_violation_times[hand_id]) < self.VIOLATION_COOLDOWN

                # ** THE VIOLATION CONDITION **
                if time_in_roi > self.PICKING_TIME_THRESHOLD and not in_cooldown:
                    # Check if any scooper is near the hand.
                    has_scooper = any(
                        (hand['bbox']['x1'] < s['center']['x'] < hand['bbox']['x2'] and
                         hand['bbox']['y1'] < s['center']['y'] < hand['bbox']['y2'])
                        for s in scoopers
                    )
                    
                    if not has_scooper:
                        # If all conditions are met, it's a violation.
                        violation = {
                            'type': 'hand_in_container_without_scooper',
                            'severity': 'high',
                            'confidence': hand.get('confidence', 0.0),
                            'bbox': hand['bbox'],
                            'timestamp': current_time,
                            'frame_id': frame_id,
                            'message': 'Hand detected in ingredient container without scooper.'
                        }
                        violations.append(violation)
                        
                        # Record the violation time to start the cooldown.
                        self.last_violation_times[hand_id] = current_time
                        logger.warning(f"VIOLATION! Hand '{hand_id}' in ROI for {time_in_roi:.2f}s without scooper.")

            else:
                # If the hand is detected but is OUTSIDE the ROI, remove it from our tracker.
                if hand_id in self.hands_in_roi_since:
                    logger.info(f"Hand '{hand_id}' left ROI.")
                    del self.hands_in_roi_since[hand_id]

        # Clean up any hands that disappeared entirely from the frame.
        stale_hands = [hand_id for hand_id in self.hands_in_roi_since if hand_id not in current_frame_hand_ids]
        for hand_id in stale_hands:
            del self.hands_in_roi_since[hand_id]
            
        return violations