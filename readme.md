# Pizza Store Scooper Violation Detection System

## 📌 Overview

This is a **microservices-based computer vision system** designed to monitor hygiene protocol compliance in a pizza store. The system detects whether workers are using a scooper when picking up ingredients (specifically proteins) from designated containers. Any action of picking up these ingredients without a scooper is flagged as a violation.

## 🎯 Key Features

- **Real-time violation detection** using a fine-tuned YOLOv8 model
- **Microservices architecture** for scalability and maintainability
- **WebSocket-based streaming** for live video display
- **Automated violation tracking** with detailed logging
- **Support for multiple workers** simultaneously
- **Intelligent logic** to distinguish between picking ingredients and cleaning actions

## 🏗️ System Architecture

The system consists of 5 main microservices:

1. **Frame Reader Service** - Ingests video and publishes frames to RabbitMQ
2. **Detection Service** - Performs object detection and violation logic
3. **Streaming Service** - Serves annotated video stream via WebSocket
4. **Frontend UI** - Displays real-time video with detections and violations
5. **Message Broker (RabbitMQ)** - Handles communication between services

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM allocated to Docker
- The fine-tuned model file: `yolo12m-v2.pt` (place in `models/` directory)
- Test videos in `data/videos/` directory

### 1. Clone the Repository

```bash
git clone <repository-url>
cd scooper-detection-system
```

### 2. Verify Model File

**CRITICAL**: Ensure the fine-tuned model is in place:

```bash
# Check if model exists
ls -lh models/yolo12m-v2.pt

# Should show a file around 50-100MB
# If not present, download from the provided link
```

### 3. Set Up ROI Configuration

The system includes an optimized ROI configuration. To customize:

```bash
# Edit roi_config.json to adjust the protein container area
nano roi_config.json
```

### 4. Build and Run

```bash
# Build all services
docker-compose build

# Start the system
docker-compose up
```

### 5. Access the System

- **Frontend Dashboard**: http://localhost:3000
- **RabbitMQ Management**: http://localhost:15672 (admin/admin)
- **API Health Check**: http://localhost:8000/api/health

## 🧪 Testing & Validation

### Expected Results

The system should detect the following violations in test videos:

| Video | Expected Violations |
|-------|-------------------|
| Sah w b3dha ghalt.mp4 | 1 |
| Sah w b3dha ghalt (2).mp4 | 2 |
| Sah w b3dha ghalt (3).mp4 | 1 |

### Running Validation Tests

```bash
# Make sure system is running first
docker-compose up -d

# Run validation script
python validate_system.py
```

### Manual Testing

1. Open http://localhost:3000
2. Select a test video from the dropdown
3. Click "Start New Stream"
4. Watch for violations in the "Recent Violations" panel
5. Verify the count matches expected values

## 🔧 Configuration

### Detection Parameters

Edit `services/detection-service/src/violation_logic.py`:

```python
PICKING_TIME_THRESHOLD = 0.3  # Time in ROI to consider picking
VIOLATION_COOLDOWN = 2.0      # Cooldown between violations
SCOOPER_ASSOCIATION_DISTANCE = 150  # Distance to associate scooper
```

### ROI Configuration

Edit `roi_config.json`:

```json
{
  "rois": [{
    "x1": 80,   // Left boundary
    "y1": 160,  // Top boundary
    "x2": 320,  // Right boundary
    "y2": 360   // Bottom boundary
  }]
}
```

### Model Confidence Thresholds

Edit `services/detection-service/src/main.py`:

```python
conf_threshold=0.3  # Detection confidence
iou_threshold=0.4   # NMS IoU threshold
```

## 📊 Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Detection service only
docker-compose logs -f detection-service

# Check for violations
docker-compose logs detection-service | grep "VIOLATION"
```

### System Statistics

The detection service logs performance metrics every 10 seconds:
- Frames processed
- Average FPS
- Total violations detected
- Per-stream violation counts

## 🐛 Troubleshooting

### Model Not Found Error

```bash
# Verify model exists
ls -la models/yolo12m-v2.pt

# Check Docker volume mount
docker-compose exec detection-service ls -la /app/models/
```

### No Violations Detected

1. Check model is loaded correctly:
```bash
docker-compose logs detection-service | grep "Model loaded"
```

2. Verify ROI covers protein container:
```bash
# ROI should be visible as blue rectangle in video
```

3. Check detection confidence:
```bash
docker-compose logs detection-service | grep "Detected"
```

### WebSocket Connection Issues

```bash
# Restart streaming service
docker-compose restart streaming-service

# Check WebSocket health
curl http://localhost:8000/api/health
```

## 📁 Project Structure

```
scooper-detection-system/
├── models/
│   └── yolo12m-v2.pt          # Fine-tuned YOLO model (REQUIRED)
├── data/
│   └── videos/                 # Test videos
├── services/
│   ├── frame-reader/           # Video ingestion service
│   ├── detection-service/      # Detection & violation logic
│   ├── streaming-service/      # WebSocket streaming
│   └── frontend/               # React UI
├── docker-compose.yml          # Service orchestration
├── roi_config.json            # ROI configuration
├── requirements.txt           # Python dependencies
└── validate_system.py         # Validation script
```

## 🔑 Key Components

### Violation Detection Logic

The system detects violations using the following sequence:

1. **Hand enters ROI** (protein container area)
2. **Hand stays in ROI** for picking threshold time (0.3s)
3. **Hand leaves ROI** and moves to pizza
4. **Check scooper presence** - if no scooper detected → VIOLATION

### Classes Detected

The fine-tuned model detects:
- `Hand` - Worker's hands
- `Person` - Workers
- `Pizza` - Pizza being prepared
- `Scooper` - Utensil for picking ingredients

## 📈 Performance Optimization

- Process frames at 10 FPS for optimal balance
- Use confidence threshold of 0.3 for better detection
- Implement hand tracking with 100px distance threshold
- Apply 2-second cooldown between violations

## 🚨 Important Notes

1. **Model Required**: The system REQUIRES the fine-tuned `yolo12m-v2.pt` model
2. **ROI Placement**: Ensure ROI covers the protein container area
3. **Multiple Workers**: System handles multiple workers simultaneously
4. **Cleaning Detection**: Long duration in ROI (>3s) is considered cleaning

## 📝 License

This project was developed as part of a Computer Vision Engineer assessment.

## 🤝 Support

For issues or questions:
1. Check the logs: `docker-compose logs`
2. Run validation: `python validate_system.py`
3. Verify model and ROI configuration

---

**Built with**: Python, FastAPI, React, Docker, RabbitMQ, YOLOv8, OpenCV