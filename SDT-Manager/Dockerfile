FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent-volume mount points
RUN mkdir -p /app/yaml_scripts /app/kubernetes /app/logs /app/data

ENV PYTHONPATH=/app
ENV SDT_INTERFACE_HOST=localhost
ENV SDT_INTERFACE_PORT=30008
ENV API_SERVER_HOST=0.0.0.0
ENV API_SERVER_PORT=8008
ENV YAML_PATH=/app/yaml_scripts/
ENV IDS_YAML_BASE_PATH=/app/kubernetes/
ENV CREDENTIAL_DB_PATH=/app/data/sdt_credentials.db
ENV LOG_LEVEL=INFO

EXPOSE 8008

RUN useradd -m -u 1000 sdtm && chown -R sdtm:sdtm /app
USER sdtm

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${API_SERVER_PORT}/health || exit 1

CMD ["python3", "main.py"]
