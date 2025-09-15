# Use Python 3.11 slim image as base (Debian-based)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /home/ubuntu/k3s-SDT-Ditto/yaml_scripts/ \
    && mkdir -p /home/ubuntu/true-connector/kubernetes/

# Set environment variables with defaults
ENV SDT_INTERFACE_HOST=localhost
ENV SDT_INTERFACE_PORT=30008
ENV API_SERVER_HOST=0.0.0.0
ENV API_SERVER_PORT=8008
ENV PYTHONPATH=/app

# Expose the API port
EXPOSE 8008

# Create a non-root user for security
RUN useradd -m -u 1000 sdt && chown -R sdt:sdt /app
USER sdt

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${API_SERVER_PORT}/status || exit 1

# Run the application
CMD ["python3", "main.py"]