#!/bin/bash
# File: /quick_setup.sh (root directory)
# Quick setup script for Pizza Store Violation Detection System

echo "================================================"
echo "Pizza Store Violation Detection - Quick Setup"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check system
echo "Step 1: Running system check..."
python3 check_system.py
if [ $? -ne 0 ]; then
    echo -e "${RED}System check failed. Please fix the issues above.${NC}"
    exit 1
fi

# Step 2: Check if ROI config exists
if [ ! -f "roi_config.json" ]; then
    echo -e "${YELLOW}ROI configuration not found.${NC}"
    echo "Step 2: Setting up ROI configuration..."
    
    # Try to find a video file for ROI configuration
    VIDEO_FILE=""
    if [ -f "data/videos/Sah w b3dha ghalt.mp4" ]; then
        VIDEO_FILE="data/videos/Sah w b3dha ghalt.mp4"
    elif [ -f "data/videos/Sah w b3dha ghalt (2).mp4" ]; then
        VIDEO_FILE="data/videos/Sah w b3dha ghalt (2).mp4"
    elif [ -f "data/videos/Sah w b3dha ghalt (3).mp4" ]; then
        VIDEO_FILE="data/videos/Sah w b3dha ghalt (3).mp4"
    fi
    
    if [ -n "$VIDEO_FILE" ]; then
        echo "Running ROI configurator with: $VIDEO_FILE"
        python3 roi_configurator.py "$VIDEO_FILE"
    else
        echo -e "${RED}No video files found for ROI configuration!${NC}"
        echo "Please add video files to data/videos/ directory"
        exit 1
    fi
else
    echo -e "${GREEN}✓ ROI configuration found${NC}"
fi

# Step 3: Optional - Test detection
echo ""
echo "Step 3: Would you like to test the detection? (y/n)"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    VIDEO_FILE="data/videos/Sah w b3dha ghalt.mp4"
    if [ -f "$VIDEO_FILE" ]; then
        python3 test_detection.py "$VIDEO_FILE"
    else
        echo -e "${YELLOW}Test video not found, skipping test${NC}"
    fi
fi

# Step 4: Docker build
echo ""
echo "Step 4: Building Docker containers..."
docker-compose down
docker-compose build

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker build failed!${NC}"
    exit 1
fi

# Step 5: Start system
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}System is ready!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "To start the system, run:"
echo "  docker-compose up"
echo ""
echo "Then open your browser to:"
echo "  http://localhost:3000"
echo ""
echo "To monitor the system in real-time, run (in another terminal):"
echo "  python3 monitor.py"
echo ""