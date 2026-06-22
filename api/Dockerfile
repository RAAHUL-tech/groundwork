FROM python:3.12-slim

WORKDIR /app

# ffmpeg for video frame extraction
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download Whisper tiny model (~40 MB int8) — fits in RAM alongside YOLO + Depth
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8')"

# Pre-download YOLOv8s weights (~22 MB)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

# Pre-download Depth Anything V2 Small (~98 MB)
RUN python -c "from transformers import pipeline; pipeline(task='depth-estimation', model='depth-anything/Depth-Anything-V2-Small-hf', device='cpu')"

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5001

CMD gunicorn "app:create_app()" --bind 0.0.0.0:${PORT:-5001} --workers 2 --timeout 120
