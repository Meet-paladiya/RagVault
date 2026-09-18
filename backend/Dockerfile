FROM python:3.11-slim

WORKDIR /app

# Install Tesseract OCR and FFmpeg for multimedia decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.txt

# Copy application code
COPY . .

# Ensure entrypoint script has LF line endings and is executable
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["/bin/sh", "/app/docker-entrypoint.sh"]
