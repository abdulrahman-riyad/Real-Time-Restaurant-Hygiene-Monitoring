import time
import logging
from collections import defaultdict, deque
from typing import List, Dict, Any, Optional
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ViolationDetector:
    """
    Enhanced violation detector with improved tracking and logic.
    Handles multiple workers and better distinguishes between cleaning and picking.
    """
    def __init__(self, roi_coords: Dict[str, float]):
        self.roi_coords = roi_coords
        
        # Track hand states over time
        self.hand_tracker: Dict[str, 'ViolationDetector.HandState'] = {}  # {hand_id: HandState}
        self.frame_history: deque = deque(maxlen=30)  # Keep 30 frames of history (~1 second at 30fps)
        
        # Thresholds
        self.PICKING_TIME_THRESHOLD = 0.8  # Increased for better accuracy
        self.CLEANING_TIME_THRESHOLD = 2.0  # Longer duration indicates cleaning
        self.VIOLATION_COOLDOWN = 5.0  # Increased cooldown
        self.MIN_HAND_MOVEMENT = 20  # Minimum pixel movement to consider action
        self.SCOOPER_PROXIMITY_THRESHOLD = 100  # Pixels distance for scooper association
        
        # Violation tracking
        self.last_violation_times: defaultdict = defaultdict(float)
        self.confirmed_violations: List[Dict[str, Any]] = []
        
        # Pizza tracking for better context
        self.pizza_positions: List[Dict[str, float]] = []

    class HandState:
        def __init__(self, hand_id: str, position: Dict[str, float]):
            self.id: str = hand_id
            self.positions: deque = deque([position], maxlen=10)  # Track last 10 positions
            # Properly type annotate these as Optional[float] since they start as None
            self.first_seen_in_roi: Optional[float] = None
            self.last_seen_in_roi: Optional[float] = None
            self.entry_time: Optional[float] = None
            self.exit_time: Optional[float] = None
            self.had_scooper: bool = False
            self.moved_to_pizza: bool = False
            self.total_movement: float = 0
            self.is_cleaning: bool = False

        def update_position(self, position: Dict[str, float]) -> None:
            if self.positions:
                last_pos = self.positions[-1]
                movement = np.sqrt((position['x'] - last_pos['x'])**2 + 
                                 (position['y'] - last_pos['y'])**2)
                self.total_movement += movement
            self.positions.append(position)

        def get_average_movement(self) -> float:
            if len(self.positions) < 2:
                return 0
            total_dist = 0
            for i in range(1, len(self.positions)):
                dist = np.sqrt((self.positions[i]['x'] - self.positions[i-1]['x'])**2 + 
                             (self.positions[i]['y'] - self.positions[i-1]['y'])**2)
                total_dist += dist
            return total_dist / (len(self.positions) - 1)

    def _get_hand_id(self, hand: Dict[str, Any], frame_id: str) -> str:
        """Enhanced hand ID generation for better tracking"""
        # Use spatial gridding for more stable tracking
        x, y = int(hand['center']['x'] / 30), int(hand['center']['y'] / 30)
        return f"hand_{x}_{y}_{frame_id[:8]}"

    def _find_closest_hand_state(self, hand: Dict[str, Any], threshold: float = 50) -> Optional[str]:
        """Find the closest existing hand state within threshold distance"""
        hand_center = hand['center']
        min_dist = float('inf')
        closest_id = None
        
        for hand_id, state in self.hand_tracker.items():
            if state.positions:
                last_pos = state.positions[-1]
                dist = np.sqrt((hand_center['x'] - last_pos['x'])**2 + 
                             (hand_center['y'] - last_pos['y'])**2)
                if dist < min_dist and dist < threshold:
                    min_dist = dist
                    closest_id = hand_id
        
        return closest_id

    def _is_in_roi(self, center: Dict[str, float]) -> bool:
        """Check if a point is within the ROI"""
        return (self.roi_coords['x1'] <= center['x'] <= self.roi_coords['x2'] and
                self.roi_coords['y1'] <= center['y'] <= self.roi_coords['y2'])

    def _is_near_pizza(self, center: Dict[str, float], threshold: float = 150) -> bool:
        """Check if hand is near any detected pizza"""
        for pizza_pos in self.pizza_positions:
            dist = np.sqrt((center['x'] - pizza_pos['x'])**2 + 
                          (center['y'] - pizza_pos['y'])**2)
            if dist < threshold:
                return True
        return False

    def _has_scooper_nearby(self, hand: Dict[str, Any], scoopers: List[Dict[str, Any]]) -> bool:
        """Enhanced scooper detection with proximity check"""
        hand_center = hand['center']
        hand_bbox = hand['bbox']
        
        for scooper in scoopers:
            scooper_center = scooper['center']
            
            # Check if scooper center is within expanded hand bbox
            expanded_margin = 50
            if (hand_bbox['x1'] - expanded_margin <= scooper_center['x'] <= hand_bbox['x2'] + expanded_margin and
                hand_bbox['y1'] - expanded_margin <= scooper_center['y'] <= hand_bbox['y2'] + expanded_margin):
                return True
            
            # Also check distance-based proximity
            dist = np.sqrt((hand_center['x'] - scooper_center['x'])**2 + 
                          (hand_center['y'] - scooper_center['y'])**2)
            if dist < self.SCOOPER_PROXIMITY_THRESHOLD:
                return True
        
        return False

    def detect_violations(self, detections: List[Dict[str, Any]], frame_id: str) -> List[Dict[str, Any]]:
        """Enhanced violation detection with multiple worker support"""
        violations: List[Dict[str, Any]] = []
        current_time = time.time()
        
        # Separate detections by type
        hands = [d for d in detections if d.get('class_name', '').lower() == 'hand']
        scoopers = [d for d in detections if d.get('class_name', '').lower() == 'scooper']
        pizzas = [d for d in detections if d.get('class_name', '').lower() == 'pizza']
        persons = [d for d in detections if d.get('class_name', '').lower() == 'person']
        
        # Update pizza positions for context
        self.pizza_positions = [p['center'] for p in pizzas]
        
        # Log detection counts for debugging
        if hands or scoopers:
            logger.debug(f"Frame {frame_id}: {len(hands)} hands, {len(scoopers)} scoopers, "
                        f"{len(pizzas)} pizzas, {len(persons)} persons")
        
        # Track current frame hands
        current_frame_hand_ids: set = set()
        
        for hand in hands:
            # Try to match with existing hand state or create new one
            existing_id = self._find_closest_hand_state(hand)
            
            if existing_id:
                hand_id = existing_id
                hand_state = self.hand_tracker[hand_id]
                hand_state.update_position(hand['center'])
            else:
                hand_id = self._get_hand_id(hand, frame_id)
                hand_state = self.HandState(hand_id, hand['center'])
                self.hand_tracker[hand_id] = hand_state
            
            current_frame_hand_ids.add(hand_id)
            
            # Check if hand has scooper
            has_scooper = self._has_scooper_nearby(hand, scoopers)
            if has_scooper:
                hand_state.had_scooper = True
            
            # Check ROI interaction
            in_roi = self._is_in_roi(hand['center'])
            near_pizza = self._is_near_pizza(hand['center'])
            
            if in_roi:
                if hand_state.entry_time is None:
                    hand_state.entry_time = current_time
                    hand_state.first_seen_in_roi = current_time
                    logger.info(f"Hand '{hand_id}' entered ROI")
                
                hand_state.last_seen_in_roi = current_time
                time_in_roi = current_time - hand_state.entry_time
                
                # Check for cleaning behavior (long duration, repetitive movement)
                if time_in_roi > self.CLEANING_TIME_THRESHOLD:
                    avg_movement = hand_state.get_average_movement()
                    if avg_movement > self.MIN_HAND_MOVEMENT:
                        hand_state.is_cleaning = True
                        logger.debug(f"Hand '{hand_id}' appears to be cleaning")
                
            else:
                # Hand is outside ROI
                if hand_state.entry_time is not None and hand_state.exit_time is None:
                    hand_state.exit_time = current_time
                    time_in_roi = hand_state.exit_time - hand_state.entry_time
                    
                    # Check if hand moved to pizza after leaving ROI
                    if near_pizza:
                        hand_state.moved_to_pizza = True
                        
                        # Check violation conditions
                        in_cooldown = (current_time - self.last_violation_times[hand_id]) < self.VIOLATION_COOLDOWN
                        
                        if (time_in_roi > self.PICKING_TIME_THRESHOLD and 
                            not hand_state.is_cleaning and
                            not hand_state.had_scooper and
                            not in_cooldown):
                            
                            violation = {
                                'type': 'hand_in_container_without_scooper',
                                'severity': 'high',
                                'confidence': hand.get('confidence', 0.0),
                                'bbox': hand['bbox'],
                                'timestamp': current_time,
                                'frame_id': frame_id,
                                'message': f'Hand grabbed ingredient from container without scooper and placed on pizza',
                                'duration_in_roi': round(time_in_roi, 2),
                                'person_count': len(persons)  # Track if multiple workers present
                            }
                            violations.append(violation)
                            self.confirmed_violations.append(violation)
                            self.last_violation_times[hand_id] = current_time
                            
                            logger.warning(f"VIOLATION DETECTED! Hand in ROI for {time_in_roi:.2f}s "
                                         f"without scooper, then moved to pizza")
                    
                    # Reset state for this hand after processing
                    if hand_state.moved_to_pizza or time_in_roi > self.CLEANING_TIME_THRESHOLD:
                        del self.hand_tracker[hand_id]
                        logger.debug(f"Hand '{hand_id}' state cleared")
        
        # Clean up stale hand states (hands that disappeared)
        stale_timeout = 2.0  # seconds
        stale_hands: List[str] = []
        for hand_id, state in self.hand_tracker.items():
            if hand_id not in current_frame_hand_ids:
                if state.last_seen_in_roi and (current_time - state.last_seen_in_roi) > stale_timeout:
                    stale_hands.append(hand_id)
        
        for hand_id in stale_hands:
            del self.hand_tracker[hand_id]
            logger.debug(f"Removed stale hand state: {hand_id}")
        
        # Store frame for history
        self.frame_history.append({
            'frame_id': frame_id,
            'timestamp': current_time,
            'hands': len(hands),
            'scoopers': len(scoopers),
            'violations': len(violations)
        })
        
        return violations

    def get_statistics(self) -> Dict[str, Any]:
        """Get violation detection statistics"""
        return {
            'total_violations': len(self.confirmed_violations),
            'active_hands': len(self.hand_tracker),
            'frames_processed': len(self.frame_history)
        }