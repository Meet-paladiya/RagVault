FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for OpenCV, ffmpeg, and building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip for better wheel handling
RUN pip install --no-cache-dir --upgrade pip

# Install CPU-only PyTorch with high timeout and retries (~2.5GB+ savings, no CUDA/NVIDIA)
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 torch --extra-index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install remaining dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

# Final cleanup: ensure no transitive NVIDIA packages were pulled
RUN pip list --format=freeze | grep -i nvidia | cut -d= -f1 | xargs -r pip uninstall -y 2>/dev/null || true

# Copy application code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["./docker-entrypoint.sh"]
