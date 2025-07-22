FROM python:3.11-slim

WORKDIR /app

# Install necessary system libraries for OpenCV
RUN apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Copy the single root requirements file and install dependencies
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy this service's source code
COPY ./services/streaming-service/src /app/src

# The command to run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]