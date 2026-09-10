FROM python:3.11-slim

WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.txt

# Copy application code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["/bin/sh", "/app/docker-entrypoint.sh"]
