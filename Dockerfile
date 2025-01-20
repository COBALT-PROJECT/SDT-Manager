# Use Ubuntu 22.04 as the base image
FROM ubuntu:22.04

# Set environment variables to prevent prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Update and install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the application files
COPY . /app

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create directories for output and test files
RUN mkdir -p /app/sdt_output /app/test_files

# Ensure entrypoint.sh is executable
RUN chmod +x entrypoint.sh

# Expose required ports
EXPOSE 8000 8005

# Set the entry point
ENTRYPOINT ["/app/entrypoint.sh"]
