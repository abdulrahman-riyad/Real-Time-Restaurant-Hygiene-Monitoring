#!/bin/bash

# Pizza Store Scooper Violation Detection System - Setup Script
# This script prepares the environment and downloads necessary files

set -e  # Exit on error

echo "========================================="
echo "Pizza Store Violation Detection Setup"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}"
echo ""

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p data/videos
mkdir -p models
mkdir -p monitoring/data

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Create ROI configuration file
echo "Creating default ROI configuration..."
cat > roi_config.json << 'EOF'
{
  "frame_width": 640,
  "frame_height": 480,
  "rois": [
    {
      "id": "roi_1",
      "name": "Main Protein Container",
      "x1": 120,
      "y1": 180,
      "x2": 280,
      "y2": 320,
      "type": "protein_container",
      "active": true
    }
  ]
}
EOF

echo -e "${GREEN}✓ ROI configuration created${NC}"
echo ""

# Check for model file
MODEL_PATH="models/yolo12m-v2.pt"
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${YELLOW}Warning: YOLO model not found at $MODEL_PATH${NC}"
    echo "The system will use the default YOLOv8 model as fallback."
    echo ""
    echo "To use the custom model:"
    echo "1. Download yolo12m-v2.pt from the provided link"
    echo "2. Place it in the ./models/ directory"
    echo ""
else
    echo -e "${GREEN}✓ YOLO model found${NC}"
fi

# Check for video files
VIDEO_DIR="data/videos"
VIDEO_COUNT=$(find "$VIDEO_DIR" -name "*.mp4" -o -name "*.avi" -o -name "*.mov" 2>/dev/null | wc -l)

if [ "$VIDEO_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}Warning: No video files found in $VIDEO_DIR${NC}"
    echo "Please add test videos to the ./data/videos/ directory"
    echo ""
    echo "Expected video files:"
    echo "  - Sah w b3dha ghalt.mp4 (1 violation)"
    echo "  - Sah w b3dha ghalt (2).mp4 (2 violations)"
    echo "  - Sah w b3dha ghalt (3).mp4 (1 violation)"
    echo ""
else
    echo -e "${GREEN}✓ Found $VIDEO_COUNT video file(s)${NC}"
    echo "Videos found:"
    find "$VIDEO_DIR" -name "*.mp4" -o -name "*.avi" -o -name "*.mov" 2>/dev/null | while read -r file; do
        echo "  - $(basename "$file")"
    done
    echo ""
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating environment file..."
    cat > .env << 'EOF'
# RabbitMQ Configuration
RABBITMQ_DEFAULT_USER=admin
RABBITMQ_DEFAULT_PASS=admin

# Model Configuration
MODEL_PATH=/app/models/yolo12m-v2.pt

# Processing Configuration
TARGET_PROCESSING_FPS=10
BROADCAST_FPS=15

# WebSocket URL for frontend
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
EOF
    echo -e "${GREEN}✓ Environment file created${NC}"
    echo ""
fi

# Build and start services
echo "========================================="
echo "Building Docker containers..."
echo "========================================="
echo ""

docker-compose build

echo ""
echo -e "${GREEN}✓ Docker containers built successfully${NC}"
echo ""

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "To start the system, run:"
echo -e "${GREEN}  docker-compose up${NC}"
echo ""
echo "Then access the dashboard at:"
echo -e "${GREEN}  http://localhost:3000${NC}"
echo ""
echo "RabbitMQ Management UI:"
echo -e "${GREEN}  http://localhost:15672${NC}"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "To stop the system:"
echo -e "${YELLOW}  docker-compose down${NC}"
echo ""
echo "For development with logs:"
echo -e "${YELLOW}  docker-compose up --build${NC}"
echo ""