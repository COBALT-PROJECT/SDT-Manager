# IDS Provider-Consumer Sync Service

A containerized Kubernetes service that automatically synchronizes TextResources from IDS Provider to Consumer, enabling Consumer access to Provider data.

## 🎯 Purpose

This service solves the Consumer-Provider federation gap by:
- **Monitoring** Provider catalog for new TextResources
- **Automatically syncing** resources to Consumer catalog  
- **Enabling Consumer access** to Provider data
- **Maintaining synchronization** in real-time

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   tc-provider   │    │  ids-sync-svc   │    │   tc-consumer   │
│    (port 8090)  │◄──►│    (pod)        │───►│    (port 8444)  │
│                 │    │                 │    │                 │
│ Provider Catalog│    │ Sync Service    │    │Consumer Catalog │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
├── Dockerfile                 # Container definition
├── requirements.txt           # Python dependencies
├── src/
│   ├── ids-sync-service.py   # Main sync service
│   └── healthcheck.py        # Health check script
├── k8s-deployment.yaml       # Kubernetes manifests
├── monitoring.yaml           # Monitoring configuration
├── build-and-deploy.sh      # Build and deploy script
├── test-deployment.sh       # Deployment test script
└── README.md                # This file
```

## 🚀 Quick Start

### Prerequisites
- Kubernetes cluster (k3s/kind/etc.)
- Docker
- kubectl configured
- tc-provider and tc-consumer services running

### 1. Build and Deploy

```bash
# Make scripts executable
chmod +x build-and-deploy.sh test-deployment.sh

# Build and deploy to Kubernetes
./build-and-deploy.sh
```

### 2. Verify Deployment

```bash
# Test the deployment
./test-deployment.sh

# Check service status
kubectl get all -l app=ids-sync-service
```

### 3. Monitor Logs

```bash
# Follow sync activity
kubectl logs -f deployment/ids-sync-service

# Check recent logs
kubectl logs deployment/ids-sync-service --tail=50
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROVIDER_URL` | `https://tc-provider:8090` | Provider service URL |
| `CONSUMER_URL` | `https://tc-consumer:8444` | Consumer service URL |
| `IDS_USERNAME` | `admin` | IDS authentication username |
| `IDS_PASSWORD` | `password` | IDS authentication password |
| `POLL_INTERVAL_SECONDS` | `30` | Sync polling interval |
| `MAX_RETRIES` | `3` | Maximum retry attempts |
| `LOG_LEVEL` | `INFO` | Logging level |
| `HEALTH_PORT` | `8080` | Health check port |

### Kubernetes Resources

The deployment creates:
- **Deployment**: Main sync service pod
- **Service**: ClusterIP service for health checks
- **Secret**: Credentials for IDS authentication
- **ConfigMap**: Service configuration

## 📊 Monitoring

### Health Checks

The service provides health endpoints:

```bash
# Port forward to access locally
kubectl port-forward service/ids-sync-service 8080:8080

# Check health
curl http://localhost:8080/health

# View Prometheus metrics
curl http://localhost:8080/metrics
```

### Kubernetes Probes

- **Liveness Probe**: Ensures container is running
- **Readiness Probe**: Confirms service is ready to sync

### Metrics

Available Prometheus metrics:
- `ids_sync_resources_synced_total` - Total resources synced
- `ids_sync_errors_total` - Total sync errors  
- `ids_sync_resources_tracked` - Currently tracked resources
- `ids_sync_service_up` - Service status (1=up, 0=down)

## 🧪 Testing

### Manual Test

```bash
# 1. Check if connectivityService syncs
kubectl exec deployment/ids-sync-service -- curl -s \
  https://tc-consumer:8444/api/offeredResource/ \
  -H "resource: https://w3id.org/idsa/autogen/textResource/connectivityService" \
  -u admin:password -k

# 2. Verify sync metrics
kubectl port-forward service/ids-sync-service 8080:8080 &
curl http://localhost:8080/metrics | grep ids_sync
```

### Automated Test

```bash
# Run deployment tests
./test-deployment.sh
```

## 🔄 Operational Commands

### Scaling

```bash
# Scale to multiple replicas (not recommended for sync service)
kubectl scale deployment ids-sync-service --replicas=1
```

### Updates

```bash
# Update container image
kubectl set image deployment/ids-sync-service \
  ids-sync=ids-sync-service:new-tag

# Rolling restart
kubectl rollout restart deployment/ids-sync-service
```

### Debugging

```bash
# Exec into container
kubectl exec -it deployment/ids-sync-service -- /bin/bash

# View detailed pod info
kubectl describe pod -l app=ids-sync-service

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp
```

## 🛠️ Development

### Local Development

```bash
# Build image locally
docker build -t ids-sync-service:dev .

# Run locally with environment variables
docker run -e PROVIDER_URL=https://your-provider:8090 \
           -e CONSUMER_URL=https://your-consumer:8444 \
           ids-sync-service:dev
```

### Customization

To modify the sync behavior:

1. Edit `src/ids-sync-service.py`
2. Rebuild container: `docker build -t ids-sync-service:custom .`
3. Update deployment: `kubectl set image deployment/ids-sync-service ids-sync=ids-sync-service:custom`

## 🚨 Troubleshooting

### Common Issues

**Pod CrashLoopBackOff**
```bash
kubectl logs deployment/ids-sync-service
kubectl describe pod -l app=ids-sync-service
```

**Service Discovery Issues**
```bash
# Check if tc-provider/tc-consumer services exist
kubectl get svc tc-provider tc-consumer

# Test connectivity from sync pod
kubectl exec deployment/ids-sync-service -- nslookup tc-provider
```

**Authentication Failures**
```bash
# Check credentials secret
kubectl get secret ids-sync-credentials -o yaml

# Verify credentials are correct
kubectl exec deployment/ids-sync-service -- printenv IDS_USERNAME
```

**Sync Not Working**
```bash
# Check sync service logs
kubectl logs -f deployment/ids-sync-service

# Verify provider has resources
kubectl exec deployment/ids-sync-service -- curl -k \
  https://tc-provider:8090/api/selfDescription/ -u admin:password
```

## 📈 Performance

### Resource Usage

- **CPU**: 100m request, 500m limit
- **Memory**: 128Mi request, 512Mi limit  
- **Storage**: Logs stored in emptyDir volume

### Scaling Considerations

- **Single Instance**: Recommended for sync service
- **Multiple Instances**: May cause duplicate syncs
- **High Availability**: Use pod disruption budgets

## 🔒 Security

### Container Security

- Runs as non-root user (`idsuser`)
- Minimal base image (python:3.11-slim)
- No privileged access required

### Network Security

- Uses ClusterIP service (internal only)
- SSL verification disabled for internal communication
- Credentials stored in Kubernetes secrets

## 📝 Logs

Log locations:
- **Container**: `/app/logs/ids-sync.log`
- **Kubernetes**: `kubectl logs deployment/ids-sync-service`

Log levels: DEBUG, INFO, WARNING, ERROR

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Test changes locally
4. Submit pull request

## 📄 License

This project is licensed under the MIT License.