import time
import logging
from collections import defaultdict, deque
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HandTracker:
    """Tracks individual hand movements and interactions"""
    def __init__(self, hand_id: str, initial_pos: Dict[str, float]):
        self.id = hand_id
        self.positions = deque([initial_pos], maxlen=30)
        self.first_seen = time.time()
        self.last_seen = time.time()
        
        # ROI interaction tracking
        self.entered_roi_time: Optional[float] = None
        self.left_roi_time: Optional[float] = None
        self.time_in_roi: float = 0.0
        self.picked_from_roi: bool = False
        
        # Scooper tracking
        self.had_scooper_in_roi: bool = False
        self.scooper_confidence: float = 0.0
        
        # Pizza interaction
        self.moved_to_pizza: bool = False
        self.pizza_interaction_time: Optional[float] = None
        
        # Movement analysis
        self.total_distance: float = 0.0
        self.is_active: bool = True
        
    def update(self, pos: Dict[str, float]):
        """Update hand position and calculate movement"""
        if self.positions:
            last_pos = self.positions[-1]
            dist = np.sqrt((pos['x'] - last_pos['x'])**2 + (pos['y'] - last_pos['y'])**2)
            self.total_distance += dist
        
        self.positions.append(pos)
        self.last_seen = time.time()
        
    def get_current_position(self) -> Dict[str, float]:
        """Get most recent position"""
        return self.positions[-1] if self.positions else {'x': 0, 'y': 0}
    
    def get_average_speed(self) -> float:
        """Calculate average movement speed"""
        if len(self.positions) < 2:
            return 0.0
        
        time_span = self.last_seen - self.first_seen
        if time_span > 0:
            return self.total_distance / time_span
        return 0.0


class PersonTracker:
    """Tracks individual persons and their hands"""
    def __init__(self, person_id: str):
        self.id = person_id
        self.associated_hands: Set[str] = set()
        self.last_seen = time.time()
        self.violations_count = 0


class ViolationDetector:
    """
    Enhanced violation detector that properly tracks the sequence:
    1. Hand enters ROI (protein container)
    2. Hand picks ingredient (stays in ROI for sufficient time)
    3. Hand leaves ROI
    4. Hand moves to pizza
    5. Check if scooper was used during the picking
    """
    
    def __init__(self, roi_coords: Dict[str, float]):
        self.roi_coords = roi_coords
        
        # Enhanced tracking for better violation detection
        self.hand_states: Dict[str, HandTracker] = {}
        self.person_trackers: Dict[str, PersonTracker] = {}
        
        # ADJUSTED THRESHOLDS FOR BETTER DETECTION
        self.PICKING_TIME_THRESHOLD = 0.2  # Reduced from 0.3 - hand needs to be in ROI for 0.2s
        self.CLEANING_TIME_THRESHOLD = 3.0  # Longer time suggests cleaning
        self.VIOLATION_COOLDOWN = 1.5  # Reduced from 2.0 for faster detection
        self.HAND_TRACKING_DISTANCE = 150  # Increased for better tracking between frames
        self.SCOOPER_ASSOCIATION_DISTANCE = 200  # Increased for better scooper detection
        self.PIZZA_PROXIMITY_THRESHOLD = 300  # Increased to detect pizza interaction better
        
        # Violation tracking
        self.violations_per_stream: Dict[str, List[Dict]] = defaultdict(list)
        self.last_violation_time: Dict[str, float] = {}
        self.frame_buffer = deque(maxlen=60)  # Keep 2 seconds of history at 30fps
        
        # Pizza tracking for context
        self.recent_pizzas: List[Dict[str, float]] = []
        self.recent_scoopers: List[Dict[str, Any]] = []
        
        # Track hands that have been in ROI and left
        self.hands_that_left_roi: Dict[str, HandTracker] = {}
        
        logger.info(f"ViolationDetector initialized with ROI: {roi_coords}")
        logger.info(f"Thresholds: picking={self.PICKING_TIME_THRESHOLD}s, cooldown={self.VIOLATION_COOLDOWN}s")

    def _find_closest_hand(self, hand_center: Dict[str, float], max_distance: float) -> Optional[str]:
        """Find the closest existing hand tracker within max_distance"""
        min_dist = float('inf')
        closest_id = None
        current_time = time.time()
        
        # Check both active hands and hands that left ROI
        all_hands = {**self.hand_states, **self.hands_that_left_roi}
        
        # Remove very old trackers
        stale_ids = []
        for hand_id, tracker in all_hands.items():
            if current_time - tracker.last_seen > 2.0:  # 2 second timeout
                stale_ids.append(hand_id)
        
        for hand_id in stale_ids:
            if hand_id in self.hand_states:
                del self.hand_states[hand_id]
            if hand_id in self.hands_that_left_roi:
                del self.hands_that_left_roi[hand_id]
        
        # Find closest tracker
        for hand_id, tracker in all_hands.items():
            if not tracker.is_active:
                continue
                
            last_pos = tracker.get_current_position()
            dist = np.sqrt((hand_center['x'] - last_pos['x'])**2 + 
                          (hand_center['y'] - last_pos['y'])**2)
            
            if dist < min_dist and dist < max_distance:
                min_dist = dist
                closest_id = hand_id
        
        return closest_id

    def _is_in_roi(self, center: Dict[str, float]) -> bool:
        """Check if a point is within the ROI"""
        return (self.roi_coords['x1'] <= center['x'] <= self.roi_coords['x2'] and
                self.roi_coords['y1'] <= center['y'] <= self.roi_coords['y2'])

    def _is_near_pizza(self, center: Dict[str, float]) -> bool:
        """Check if hand is near any detected pizza"""
        # If no pizzas detected, assume there might be one in the preparation area
        if not self.recent_pizzas:
            # Check if hand is in typical pizza preparation area (lower part of frame)
            if center['y'] > 300:  # Lower half of frame where pizzas usually are
                return True
        
        for pizza_pos in self.recent_pizzas:
            dist = np.sqrt((center['x'] - pizza_pos['x'])**2 + 
                          (center['y'] - pizza_pos['y'])**2)
            if dist < self.PIZZA_PROXIMITY_THRESHOLD:
                return True
        return False

    def _check_scooper_association(self, hand_bbox: Dict[str, float]) -> Tuple[bool, float]:
        """Check if a scooper is associated with the hand"""
        if not self.recent_scoopers:
            return False, 0.0
        
        hand_center_x = (hand_bbox['x1'] + hand_bbox['x2']) / 2
        hand_center_y = (hand_bbox['y1'] + hand_bbox['y2']) / 2
        
        best_confidence = 0.0
        for scooper in self.recent_scoopers:
            # Get scooper center coordinates
            scooper_center_x: float = 0.0
            scooper_center_y: float = 0.0
            
            # Handle different scooper data formats
            if 'bbox' in scooper and isinstance(scooper['bbox'], dict):
                scooper_bbox = scooper['bbox']
                scooper_center_x = (scooper_bbox['x1'] + scooper_bbox['x2']) / 2
                scooper_center_y = (scooper_bbox['y1'] + scooper_bbox['y2']) / 2
            elif 'center' in scooper and isinstance(scooper['center'], dict):
                scooper_center_x = scooper['center']['x']
                scooper_center_y = scooper['center']['y']
            else:
                continue
            
            # Calculate distance between hand and scooper
            dist = np.sqrt((hand_center_x - scooper_center_x)**2 + 
                          (hand_center_y - scooper_center_y)**2)
            
            if dist < self.SCOOPER_ASSOCIATION_DISTANCE:
                confidence = scooper.get('confidence', 0.5)
                best_confidence = max(best_confidence, confidence)
                
                # Check for bounding box overlap
                if 'bbox' in scooper and isinstance(scooper['bbox'], dict):
                    scooper_bbox = scooper['bbox']
                    x_overlap = max(0, min(hand_bbox['x2'], scooper_bbox['x2']) - 
                                   max(hand_bbox['x1'], scooper_bbox['x1']))
                    y_overlap = max(0, min(hand_bbox['y2'], scooper_bbox['y2']) - 
                                   max(hand_bbox['y1'], scooper_bbox['y1']))
                    
                    if x_overlap > 0 and y_overlap > 0:
                        best_confidence = min(1.0, best_confidence + 0.3)
        
        return best_confidence > 0.2, best_confidence  # Lower threshold for better detection

    def detect_violations(self, detections: List[Dict[str, Any]], frame_id: str, 
                          stream_id: str = "default") -> List[Dict[str, Any]]:
        """
        Main violation detection logic following the exact sequence
        """
        violations: List[Dict[str, Any]] = []
        current_time = time.time()
        
        # Separate detections by class
        hands: List[Dict[str, Any]] = []
        scoopers: List[Dict[str, Any]] = []
        pizzas: List[Dict[str, Any]] = []
        persons: List[Dict[str, Any]] = []
        
        for d in detections:
            class_name = d.get('class_name', '').lower()
            if 'hand' in class_name:
                hands.append(d)
            elif 'scooper' in class_name:
                scoopers.append(d)
            elif 'pizza' in class_name:
                pizzas.append(d)
            elif 'person' in class_name:
                persons.append(d)
        
        # Update recent detections for context
        self.recent_pizzas = []
        for p in pizzas:
            if 'center' in p and isinstance(p['center'], dict):
                self.recent_pizzas.append(p['center'])
            elif 'bbox' in p and isinstance(p['bbox'], dict):
                bbox = p['bbox']
                self.recent_pizzas.append({
                    'x': (bbox['x1'] + bbox['x2']) / 2,
                    'y': (bbox['y1'] + bbox['y2']) / 2
                })
        
        self.recent_scoopers = scoopers
        
        # Log detection counts periodically
        if len(self.frame_buffer) % 30 == 0 and (hands or scoopers):
            logger.debug(f"Frame {frame_id}: {len(hands)} hands, {len(scoopers)} scoopers, "
                        f"{len(pizzas)} pizzas, {len(persons)} persons")
        
        # Process each detected hand
        for hand in hands:
            hand_center = hand.get('center')
            if not hand_center or not isinstance(hand_center, dict):
                continue
            
            hand_bbox = hand.get('bbox')
            if not hand_bbox or not isinstance(hand_bbox, dict):
                continue
            
            # Find or create hand tracker
            hand_id = self._find_closest_hand(hand_center, self.HAND_TRACKING_DISTANCE)
            
            if hand_id:
                # Move tracker back to active if it was in the left_roi dict
                if hand_id in self.hands_that_left_roi:
                    tracker = self.hands_that_left_roi.pop(hand_id)
                    self.hand_states[hand_id] = tracker
                else:
                    tracker = self.hand_states.get(hand_id)
                
                if tracker:
                    tracker.update(hand_center)
            else:
                # Create new tracker
                hand_id = f"hand_{stream_id}_{frame_id}_{len(self.hand_states)}"
                tracker = HandTracker(hand_id, hand_center)
                self.hand_states[hand_id] = tracker
            
            # Check if hand is in ROI
            in_roi = self._is_in_roi(hand_center)
            
            # Check for scooper association
            has_scooper, scooper_conf = self._check_scooper_association(hand_bbox)
            
            # Update tracker state based on ROI interaction
            if in_roi:
                if tracker.entered_roi_time is None:
                    # Hand just entered ROI
                    tracker.entered_roi_time = current_time
                    logger.info(f"Hand {hand_id} entered ROI")
                
                # Update time in ROI
                tracker.time_in_roi = current_time - tracker.entered_roi_time
                
                # Check if scooper is being used
                if has_scooper:
                    tracker.had_scooper_in_roi = True
                    tracker.scooper_confidence = max(tracker.scooper_confidence, scooper_conf)
                    logger.debug(f"Hand {hand_id} has scooper (conf: {scooper_conf:.2f})")
                
                # Check if this is a picking action
                if tracker.time_in_roi >= self.PICKING_TIME_THRESHOLD and not tracker.picked_from_roi:
                    tracker.picked_from_roi = True
                    logger.info(f"Hand {hand_id} picked from ROI (time: {tracker.time_in_roi:.2f}s, "
                               f"scooper: {tracker.had_scooper_in_roi})")
                
            else:  # Hand is outside ROI
                if tracker.entered_roi_time is not None and tracker.picked_from_roi:
                    # Hand was in ROI and picked something, now it left
                    if tracker.left_roi_time is None:
                        tracker.left_roi_time = current_time
                        logger.info(f"Hand {hand_id} left ROI after {tracker.time_in_roi:.2f}s")
                        
                        # Move to hands_that_left_roi for tracking
                        self.hands_that_left_roi[hand_id] = tracker
                        if hand_id in self.hand_states:
                            del self.hand_states[hand_id]
                    
                    # Check if hand moved to pizza
                    if self._is_near_pizza(hand_center) and not tracker.moved_to_pizza:
                        tracker.moved_to_pizza = True
                        tracker.pizza_interaction_time = current_time
                        
                        # CHECK FOR VIOLATION NOW
                        cooldown_key = f"{stream_id}_{hand_id}"
                        in_cooldown = (cooldown_key in self.last_violation_time and 
                                     current_time - self.last_violation_time[cooldown_key] < self.VIOLATION_COOLDOWN)
                        
                        if not tracker.had_scooper_in_roi and not in_cooldown:
                            # VIOLATION DETECTED!
                            violation = {
                                'id': f"violation_{stream_id}_{frame_id}_{len(violations)}",
                                'type': 'hand_picked_without_scooper',
                                'severity': 'high',
                                'confidence': hand.get('confidence', 0.0),
                                'bbox': hand_bbox,
                                'timestamp': current_time,
                                'frame_id': frame_id,
                                'stream_id': stream_id,
                                'message': 'Worker picked ingredient from protein container without using scooper',
                                'details': {
                                    'time_in_roi': round(tracker.time_in_roi, 2),
                                    'hand_id': hand_id,
                                    'person_count': len(persons)
                                }
                            }
                            
                            violations.append(violation)
                            self.violations_per_stream[stream_id].append(violation)
                            self.last_violation_time[cooldown_key] = current_time
                            
                            # Mark tracker as processed
                            tracker.is_active = False
                            
                            logger.warning(f"🚨 VIOLATION DETECTED in {stream_id}! "
                                         f"Hand picked from ROI for {tracker.time_in_roi:.2f}s without scooper, "
                                         f"then moved to pizza")
                        
                        elif tracker.had_scooper_in_roi:
                            logger.info(f"✅ No violation - Hand {hand_id} used scooper")
                        
                        elif in_cooldown:
                            logger.debug(f"Potential violation in cooldown for {hand_id}")
        
        # Store frame data for history
        self.frame_buffer.append({
            'frame_id': frame_id,
            'timestamp': current_time,
            'hands': len(hands),
            'scoopers': len(scoopers),
            'pizzas': len(pizzas),
            'violations': len(violations)
        })
        
        return violations

    def get_statistics(self) -> Dict[str, Any]:
        """Get violation detection statistics"""
        total_violations = sum(len(v) for v in self.violations_per_stream.values())
        
        stats = {
            'total_violations': total_violations,
            'active_hand_trackers': len([t for t in self.hand_states.values() if t.is_active]),
            'hands_that_left_roi': len(self.hands_that_left_roi),
            'frames_in_buffer': len(self.frame_buffer),
            'streams_monitored': len(self.violations_per_stream)
        }
        
        # Add per-stream violation counts
        for stream_id, violations in self.violations_per_stream.items():
            stats[f'violations_{stream_id}'] = len(violations)
        
        return stats

    def reset_stream(self, stream_id: str):
        """Reset tracking for a specific stream"""
        if stream_id in self.violations_per_stream:
            del self.violations_per_stream[stream_id]
        
        # Clear hand trackers for this stream
        to_remove = [hid for hid in self.hand_states.keys() if stream_id in hid]
        for hid in to_remove:
            del self.hand_states[hid]
        
        to_remove = [hid for hid in self.hands_that_left_roi.keys() if stream_id in hid]
        for hid in to_remove:
            del self.hands_that_left_roi[hid]
        
        logger.info(f"Reset tracking for stream: {stream_id}")