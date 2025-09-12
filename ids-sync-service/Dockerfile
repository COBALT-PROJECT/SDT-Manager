# IDS Provider-Consumer Sync Service Container
FROM python:3.11-slim

# Metadata
LABEL maintainer="IDS Team"
LABEL description="IDS Provider-Consumer Synchronization Service"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV APP_HOME=/app

# Create app directory
WORKDIR ${APP_HOME}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ .

# Create non-root user for security
RUN groupadd -r idsuser && useradd -r -g idsuser idsuser
RUN chown -R idsuser:idsuser ${APP_HOME}

# Create logs directory
RUN mkdir -p /app/logs && chown -R idsuser:idsuser /app/logs

# Switch to non-root user
USER idsuser

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python healthcheck.py || exit 1

# Expose port for health checks and metrics
EXPOSE 8080

# Default command
CMD ["python", "ids-sync-service.py"]