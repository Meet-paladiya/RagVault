# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for video/audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels from builder
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install dependencies from wheels
RUN pip install --no-cache /wheels/*

# Create necessary directories
RUN mkdir -p /uploads/temp /hf_cache

# Set environment variables
ENV HF_HOME=/hf_cache
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY . .

# Make entrypoint script executable
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
