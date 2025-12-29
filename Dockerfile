# Family Finance - Bank Statement Parser
# Watches for CSV files and imports to PostgreSQL database

FROM python:3.11-slim

LABEL maintainer="jack"
LABEL description="Bank statement parser and file watcher service"

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY src/ ./src/
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for incoming files
RUN mkdir -p /incoming

# Environment variables with defaults (DB credentials set at runtime via Ansible)
ENV WATCH_DIR=/incoming
ENV POLL_INTERVAL=30
ENV DB_TYPE=postgres

# Run the file watcher
CMD ["python", "-m", "src.watcher"]
