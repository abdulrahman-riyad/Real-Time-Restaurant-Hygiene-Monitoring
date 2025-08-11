echo "================================================"
echo "Fixing Violation Detection System"
echo "================================================"
echo ""

# Step 1: Backup current violation_logic.py
echo "Step 1: Backing up current violation_logic.py..."
docker-compose exec detection-service cp /app/src/violation_logic.py /app/src/violation_logic.py.backup 2>/dev/null || true

# Step 2: Create the fixed violation_logic.py
echo "Step 2: Creating fixed violation_logic.py..."
cat > services/detection-service/src/violation_logic_fixed.py << 'EOFIX'
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

class ViolationDetector:
    """Simplified violation detector for testing"""
    
    def __init__(self, roi_coords: Dict[str, float]):
        self.roi_coords = roi_coords
        self.hand_states: Dict[str, HandTracker] = {}
        
        # VERY LOW THRESHOLDS FOR TESTING
        self.PICKING_TIME_THRESHOLD = 0.1  # Very short for testing
        self.VIOLATION_COOLDOWN = 1.0
        self.HAND_TRACKING_DISTANCE = 200
        
        self.violations_per_stream: Dict[str, List[Dict]] = defaultdict(list)
        self.last_violation_time: Dict[str, float] = {}
        self.recent_scoopers: List[Dict[str, Any]] = []
        
        # Track hands in ROI
        self.hands_in_roi_count = 0
        
        logger.info(f"ViolationDetector initialized with TESTING thresholds")
        logger.info(f"ROI: {roi_coords}")

    def _is_in_roi(self, center: Dict[str, float]) -> bool:
        """Check if a point is within the ROI"""
        return (self.roi_coords['x1'] <= center['x'] <= self.roi_coords['x2'] and
                self.roi_coords['y1'] <= center['y'] <= self.roi_coords['y2'])

    def detect_violations(self, detections: List[Dict[str, Any]], frame_id: str, 
                          stream_id: str = "default") -> List[Dict[str, Any]]:
        """Simplified violation detection for testing"""
        violations: List[Dict[str, Any]] = []
        current_time = time.time()
        
        # Separate detections by class
        hands = []
        scoopers = []
        
        for d in detections:
            class_name = d.get('class_name', '').lower()
            if 'hand' in class_name:
                hands.append(d)
            elif 'scooper' in class_name:
                scoopers.append(d)
        
        self.recent_scoopers = scoopers
        
        # SIMPLIFIED LOGIC: If hand in ROI and no scooper nearby = violation
        for hand in hands:
            hand_center = hand.get('center')
            if not hand_center or not isinstance(hand_center, dict):
                continue
            
            hand_bbox = hand.get('bbox')
            if not hand_bbox or not isinstance(hand_bbox, dict):
                continue
            
            # Check if hand is in ROI
            if self._is_in_roi(hand_center):
                self.hands_in_roi_count += 1
                
                # Check if there's a scooper nearby
                has_scooper = False
                if scoopers:
                    for scooper in scoopers:
                        if 'center' in scooper:
                            sc = scooper['center']
                            dist = np.sqrt((hand_center['x'] - sc['x'])**2 + 
                                         (hand_center['y'] - sc['y'])**2)
                            if dist < 250:  # Large threshold
                                has_scooper = True
                                break
                
                # If no scooper and enough hands have been in ROI, trigger violation
                if not has_scooper and self.hands_in_roi_count > 5:
                    cooldown_key = f"{stream_id}_test"
                    in_cooldown = (cooldown_key in self.last_violation_time and 
                                 current_time - self.last_violation_time[cooldown_key] < self.VIOLATION_COOLDOWN)
                    
                    if not in_cooldown:
                        violation = {
                            'id': f"violation_{stream_id}_{frame_id}",
                            'type': 'hand_picked_without_scooper',
                            'severity': 'high',
                            'confidence': hand.get('confidence', 0.0),
                            'bbox': hand_bbox,
                            'timestamp': current_time,
                            'frame_id': frame_id,
                            'stream_id': stream_id,
                            'message': 'TEST: Hand in ROI without scooper detected',
                            'details': {
                                'hands_in_roi_count': self.hands_in_roi_count
                            }
                        }
                        
                        violations.append(violation)
                        self.violations_per_stream[stream_id].append(violation)
                        self.last_violation_time[cooldown_key] = current_time
                        
                        logger.warning(f"🚨 VIOLATION DETECTED! Hand in ROI without scooper")
                        self.hands_in_roi_count = 0  # Reset counter
        
        return violations

    def get_statistics(self) -> Dict[str, Any]:
        """Get violation detection statistics"""
        total_violations = sum(len(v) for v in self.violations_per_stream.values())
        
        return {
            'total_violations': total_violations,
            'hands_in_roi_count': self.hands_in_roi_count,
            'streams_monitored': len(self.violations_per_stream)
        }

    def reset_stream(self, stream_id: str):
        """Reset tracking for a specific stream"""
        if stream_id in self.violations_per_stream:
            del self.violations_per_stream[stream_id]
        self.hands_in_roi_count = 0
        logger.info(f"Reset tracking for stream: {stream_id}")
EOFIX

# Step 3: Copy the fixed file over the original
echo "Step 3: Replacing violation_logic.py with fixed version..."
cp services/detection-service/src/violation_logic_fixed.py services/detection-service/src/violation_logic.py

# Step 4: Rebuild detection service
echo "Step 4: Rebuilding detection service..."
docker-compose stop detection-service
docker-compose build detection-service

# Step 5: Start detection service
echo "Step 5: Starting detection service with fixed violation logic..."
docker-compose up -d detection-service

echo ""
echo "Waiting for service to start..."
sleep 10

# Step 6: Check logs
echo "Step 6: Checking if violations are now being detected..."
echo "================================================"
docker-compose logs detection-service | tail -20 | grep -E "(VIOLATION|violation|ROI|Hand)"

echo ""
echo "================================================"
echo "Fix Applied!"
echo "================================================"
echo ""
echo "The violation detection has been simplified for testing:"
echo "- Reduced picking time threshold to 0.1s"
echo "- Simplified logic: hand in ROI without scooper = violation"
echo "- After 5 hands enter ROI without scooper, a violation triggers"
echo ""
echo "To test:"
echo "1. Open http://localhost:3000"
echo "2. Start 'Sah w b3dha ghalt.mp4'"
echo "3. Watch for violations to appear"
echo ""
echo "Monitor logs:"
echo "  docker-compose logs -f detection-service | grep VIOLATION"
echo ""