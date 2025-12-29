# Family Finance - Bank Statement Parser
# Watches for CSV files and imports to SQLite database

FROM python:3.11-slim

LABEL maintainer="jack"
LABEL description="Bank statement parser and file watcher service"

# Set working directory
WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY requirements.txt ./

# Install dependencies (none required for basic functionality)
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for data and incoming files
# These will typically be mounted as volumes
RUN mkdir -p /data /incoming

# Environment variables with defaults
ENV WATCH_DIR=/incoming
ENV DATA_DIR=/data
ENV POLL_INTERVAL=30

# Run the file watcher
CMD ["python", "-m", "src.watcher"]
