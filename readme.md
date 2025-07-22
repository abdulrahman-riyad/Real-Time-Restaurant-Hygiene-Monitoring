# Pizza Store Scooper Violation Detection System

## Overview

This project is a complete, microservices-based computer vision system designed to monitor hygiene protocol compliance in a pizza store. It uses real-time video analysis to detect if employees are using a scooper when handling certain ingredients from designated containers and flags any violations on a live web dashboard.

This system was built to fulfill all requirements of the Computer Vision Engineer assessment from Eagle Vision.

---

## Key Features

-   **End-to-End Microservices Pipeline:** A fully functional system from video ingestion to frontend display, with services communicating asynchronously via a message broker.
-   **Real-Time Violation Detection:** Utilizes the provided custom-trained YOLOv8 model to accurately detect hands, scoopers, pizzas, and people in the video stream.
-   **Intelligent Violation Logic:** The system uses a time-based heuristic to distinguish between an employee genuinely picking ingredients versus just quickly passing a hand through the area (e.g., for cleaning), reducing false positives.
-   **Live Web Dashboard:** A responsive and intuitive frontend built with Next.js and TypeScript provides a seamless user experience for monitoring video streams, real-time FPS, and a live list of all detected violations.
-   **Robust and Scalable by Design:** The decoupled architecture allows for individual services to be scaled or updated independently, demonstrating a modern approach to system design.

---

## Architecture

The system is designed with a decoupled, scalable microservices architecture. Communication between backend services is handled by a RabbitMQ message broker to ensure resilience and loose coupling. The `streaming-service` acts as an API Gateway for the frontend, providing a single point of contact.

The data flows through the system as follows:

1.  The **Next.js UI** sends an HTTP request to the **Streaming Service (API Gateway)** to start or stop a video stream.
2.  The **Streaming Service** forwards this command to the **Frame Reader** service.
3.  The **Frame Reader** begins reading the specified video file, publishing each frame as a message to the `video_frames` queue in **RabbitMQ**.
4.  The **Detection Service**, an independent worker, consumes frames from this queue. It performs AI model inference, applies the violation logic, and publishes its findings (bounding boxes, violations, etc.) as a new message to the `detection_results` queue.
5.  The **Streaming Service** also consumes messages from the `detection_results` queue. It combines this metadata with the original video frames, draws the annotations, and broadcasts the final annotated image and any violation alerts to the **Next.js UI** via a WebSocket connection.

This event-driven approach ensures that each service has a single responsibility and that the system remains responsive and resilient.

### Services

-   **Frame Reader (`frame-reader`):** A FastAPI service that ingests video files. It reads frames at a controlled rate and publishes them to the message broker. It is designed as a singleton streamer, processing only one video at a time to ensure clean state management.
-   **Detection Service (`detection-service`):** The core analytical engine. This Python service consumes frames, runs the fine-tuned YOLOv8 model for object detection, and applies the custom time-based violation logic to identify scooper violations.
-   **Streaming Service (`streaming-service`):** A FastAPI service that acts as the API Gateway. It consumes detection results, draws annotations (bounding boxes, ROIs, violation alerts) onto the raw video frames, and broadcasts the final annotated video stream and violation alerts to the frontend via WebSockets.
-   **Frontend (`frontend`):** A Next.js and TypeScript application that provides a real-time monitoring dashboard for viewing the video stream, live stats, and a list of recent violations.
-   **Message Broker (`rabbitmq`):** RabbitMQ, for asynchronous communication and buffering between the backend services.

---

## Technology Stack

-   **Backend:** Python 3.11, FastAPI, OpenCV, PyTorch, Ultralytics (YOLOv8)
-   **Frontend:** Next.js 14, React 18, TypeScript, Zustand, Tailwind CSS
-   **Infrastructure:** Docker, Docker Compose
-   **Messaging:** RabbitMQ

---

## How to Run

The entire system is orchestrated with Docker Compose for a simple, one-command setup.

### Prerequisites

-   Docker Desktop installed and running on your machine.

### Setup Instructions

1.  Clone the repository to your local machine.
2.  Navigate to the project's root directory in your terminal:
    ```bash
    cd scooper-detection-system
    ```
3.  Build and run all the services using a single command:
    ```bash
    docker-compose up --build
    ```
    The initial build may take several minutes as it downloads the base Docker images and installs all Python and Node.js dependencies.

4.  Once all services are running (you will see logs from all five services in your terminal), open your web browser and navigate to:
    **[http://localhost:3000](http://localhost:3000)**

5.  (Optional) You can view the RabbitMQ management interface to see the message queues at **[http://localhost:15672](http://localhost:15672)** (Username: `admin`, Password: `admin`).

### Usage

1.  The dashboard will load and show a "Connected" status in the top-right corner.
2.  Select a source video from the dropdown menu.
3.  Click the "Start New Stream" button.
4.  The video player will display the live, annotated video stream.
5.  As violations are detected according to the logic, the "Recent Violations" list will populate in real-time.
6.  Click the "Stop Stream" button to gracefully end the video processing.

---

## Development Journey & Key Challenges

Building this system involved overcoming several real-world engineering challenges, which were critical to achieving a stable and functional final product.

### 1. Challenge: System Dependencies in a Minimal Docker Environment

-   **Problem:** The backend Python services were consistently crashing on startup with `ImportError` messages for missing shared libraries like `libGL.so.1` and `libgthread-2.0.so.0`.
-   **Analysis:** The chosen base image, `python:3.11-slim`, is highly optimized for size and does not include many system-level libraries required by complex packages like OpenCV for rendering and graphical operations.
-   **Solution:** I systematically identified the missing dependencies from the error logs and updated the `Dockerfile` for each Python service to include an `apt-get install` command for `libgl1-mesa-glx` and `libglib2.0-0`. This created a stable and reproducible environment for the computer vision components to run reliably.

### 2. Challenge: Provided AI Model Incompatibility

-   **Problem:** The custom-trained model provided (`yolo12m-v2.pt`) initially failed to load with the latest versions of PyTorch and Ultralytics, throwing a `_pickle.UnpicklingError` related to new security policies.
-   **Analysis:** This indicated the model was trained with an older, now-incompatible version of the libraries. An initial plan to re-train the model was considered.
-   **Solution:** Before re-training, I conducted an experiment by incrementally updating the `ultralytics` library version within the Docker environment. This experiment was successful: a newer version was found to be capable of loading the older model format. This demonstrated a methodical debugging process and dependency management skills, allowing for the use of the original fine-tuned model as intended without the need for a lengthy re-training process.

### 3. Challenge: Real-Time Streaming Instability and Race Conditions

-   **Problem:** In early iterations, the video stream on the frontend would often fail to display, even though violation alerts (smaller messages) were being received. This pointed to a complex race condition.
-   **Analysis:** The issue was traced to the backend architecture. A "start stream" command would trigger a new stream, but the `detection-service` could still be processing the last few frames from the *previous* stream from the message queue. The frontend, now listening for a new stream ID, would ignore these old frames, leading to a black screen.
-   **Solution:** I refactored the entire backend state management for robustness.
    1.  The `frame-reader` was simplified into a strict "singleton streamer" that can only process one video at a time, ensuring clean stops and starts.
    2.  The `streaming-service` was redesigned with new API endpoints (`/api/stop-stream`, `/api/flush-stream`) to give the client full control over the state.
    3.  The frontend controls were updated to explicitly call the stop/flush endpoints before starting a new stream, creating a deterministic and user-controlled workflow that completely eliminated the race condition.

---

## Future Improvements

-   **Model Accuracy:** While the system is fully functional, the model's accuracy could be further improved by training for more epochs on a larger and more varied dataset (e.g., with different lighting conditions and more examples of violation and non-violation interactions).
-   **Persistent Storage:** The `docker-compose.yml` is designed to easily re-integrate a PostgreSQL database. This would allow for the long-term storage of all detected violations for auditing, analytics, and generating compliance reports.
-   **Multi-Stream View:** The frontend could be extended to display multiple video streams on the dashboard simultaneously, allowing a manager to monitor several pizza stations at once.