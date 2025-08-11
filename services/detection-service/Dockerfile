FROM python:3.11-slim

WORKDIR /app

# Install necessary system libraries for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install dependencies
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy this service's source code
COPY ./services/detection-service/src /app/src

# Create directories for models and config
RUN mkdir -p /app/models /app/config

# Create a default ROI config file (will be overridden by volume mount if exists)
RUN echo '{ \
  "frame_width": 640, \
  "frame_height": 480, \
  "rois": [ \
    { \
      "id": "roi_1", \
      "name": "Main Protein Container", \
      "x1": 80, \
      "y1": 160, \
      "x2": 320, \
      "y2": 360, \
      "type": "protein_container", \
      "active": true \
    } \
  ] \
}' > /app/roi_config.json

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV MODEL_PATH=/app/models/yolo12m-v2.pt
ENV RABBITMQ_URL=amqp://admin:admin@rabbitmq:5672/

# The command to run the application
CMD ["python", "src/main.py"]