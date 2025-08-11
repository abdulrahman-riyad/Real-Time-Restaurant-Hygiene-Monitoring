#!/bin/bash

# Pizza Store Violation Detection System - Startup Script
# This script ensures everything is properly configured before starting

set -e

echo "================================================"
echo "Pizza Store Violation Detection System"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if file exists
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} Found: $1"
        return 0
    else
        echo -e "${RED}✗${NC} Missing: $1"
        return 1
    fi
}

# Step 1: Check critical files
echo "Step 1: Checking critical files..."
echo "--------------------------------"

MODEL_OK=true
if ! check_file "models/yolo12m-v2.pt"; then
    MODEL_OK=false
    echo -e "${RED}CRITICAL: The fine-tuned model is required!${NC}"
    echo "Please download yolo12m-v2.pt and place it in the models/ directory"
fi

check_file "roi_config.json" || echo -e "${YELLOW}Warning: Using default ROI configuration${NC}"
check_file "docker-compose.yml" || exit 1
check_file "requirements.txt" || exit 1

if [ "$MODEL_OK" = false ]; then
    echo ""
    echo -e "${RED}Cannot start without the model file!${NC}"
    exit 1
fi

# Check model size
MODEL_SIZE=$(du -m models/yolo12m-v2.pt | cut -f1)
if [ "$MODEL_SIZE" -lt 10 ]; then
    echo -e "${RED}Warning: Model file seems too small (${MODEL_SIZE}MB)${NC}"
    echo "This might indicate a corrupted file."
fi

echo ""

# Step 2: Check for test videos
echo "Step 2: Checking test videos..."
echo "--------------------------------"

VIDEO_COUNT=0
for video in "Sah w b3dha ghalt.mp4" "Sah w b3dha ghalt (2).mp4" "Sah w b3dha ghalt (3).mp4"; do
    if check_file "data/videos/$video"; then
        VIDEO_COUNT=$((VIDEO_COUNT + 1))
    fi
done

if [ "$VIDEO_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}Warning: No test videos found${NC}"
    echo "Add test videos to data/videos/ directory"
else
    echo -e "${GREEN}Found $VIDEO_COUNT test video(s)${NC}"
fi

echo ""

# Step 3: Check Docker
echo "Step 3: Checking Docker..."
echo "--------------------------------"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Docker daemon is not running${NC}"
    echo "Please start Docker Desktop"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker is running"

# Check if any containers are already running
if [ "$(docker ps -q -f name=rabbitmq)" ] || [ "$(docker ps -q -f name=detection-service)" ]; then
    echo -e "${YELLOW}Some containers are already running${NC}"
    echo "Stopping existing containers..."
    docker-compose down
    sleep 2
fi

echo ""

# Step 4: Build and start services
echo "Step 4: Starting services..."
echo "--------------------------------"

echo "Building Docker images (this may take a few minutes)..."
docker-compose build

echo ""
echo "Starting services..."
docker-compose up -d

# Wait for services to be ready
echo ""
echo "Waiting for services to initialize..."

# Wait for RabbitMQ
echo -n "RabbitMQ: "
for i in {1..30}; do
    if docker exec rabbitmq rabbitmq-diagnostics ping &> /dev/null; then
        echo -e "${GREEN}Ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for detection service
echo -n "Detection Service: "
for i in {1..20}; do
    if docker logs detection-service 2>&1 | grep -q "Model loaded successfully"; then
        echo -e "${GREEN}Ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for streaming service
echo -n "Streaming Service: "
for i in {1..20}; do
    if curl -s http://localhost:8000/api/health > /dev/null; then
        echo -e "${GREEN}Ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for frontend
echo -n "Frontend: "
for i in {1..20}; do
    if curl -s http://localhost:3000 > /dev/null; then
        echo -e "${GREEN}Ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""

# Step 5: Verify system status
echo "Step 5: System Status"
echo "--------------------------------"

# Check if all containers are running
RUNNING=$(docker-compose ps --services --filter "status=running" | wc -l)
EXPECTED=5

if [ "$RUNNING" -eq "$EXPECTED" ]; then
    echo -e "${GREEN}✓ All $EXPECTED services are running${NC}"
else
    echo -e "${YELLOW}⚠ Only $RUNNING/$EXPECTED services are running${NC}"
    echo "Check logs with: docker-compose logs"
fi

# Check model loading
if docker logs detection-service 2>&1 | grep -q "YOLO Model Successfully Loaded"; then
    echo -e "${GREEN}✓ Model loaded successfully${NC}"
else
    echo -e "${YELLOW}⚠ Check model loading status${NC}"
fi

# Display violation expectations
echo ""
echo "Expected Violations in Test Videos:"
echo "-----------------------------------"
echo "  • Sah w b3dha ghalt.mp4: 1 violation"
echo "  • Sah w b3dha ghalt (2).mp4: 2 violations"
echo "  • Sah w b3dha ghalt (3).mp4: 1 violation"

echo ""
echo "================================================"
echo -e "${GREEN}System is ready!${NC}"
echo "================================================"
echo ""
echo "Access the system at:"
echo "  • Frontend: http://localhost:3000"
echo "  • RabbitMQ: http://localhost:15672 (admin/admin)"
echo "  • API Health: http://localhost:8000/api/health"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "To run validation tests:"
echo "  python validate_system.py"
echo ""
echo "To stop the system:"
echo "  docker-compose down"
echo ""