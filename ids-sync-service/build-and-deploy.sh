#!/bin/bash

# Build and Deploy IDS Sync Service to Kubernetes
# Usage: ./build-and-deploy.sh

set -e

# Configuration
IMAGE_NAME="ids-sync-service"
IMAGE_TAG="latest"
NAMESPACE="default"

echo "🚀 Building and Deploying IDS Sync Service"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running in the correct directory
if [[ ! -f "Dockerfile" ]]; then
    print_error "Dockerfile not found. Please run this script from the project root directory."
    exit 1
fi

# Step 1: Create source directory if it doesn't exist
print_info "Creating source directory structure..."
mkdir -p src

# Step 2: Build Docker image
print_info "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
sudo docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

if [[ $? -eq 0 ]]; then
    print_status "Docker image built successfully"
else
    print_error "Docker build failed"
    exit 1
fi

# Step 3: Load image into k3s (if using k3s)
print_info "Loading image into k3s..."
if command -v k3s &> /dev/null; then
    docker save ${IMAGE_NAME}:${IMAGE_TAG} | sudo k3s ctr images import -
    print_status "Image loaded into k3s"
elif command -v kind &> /dev/null; then
    kind load docker-image ${IMAGE_NAME}:${IMAGE_TAG}
    print_status "Image loaded into kind"
else
    print_warning "Using regular Kubernetes - ensure image is available in cluster"
fi

# Step 4: Apply Kubernetes manifests
print_info "Deploying to Kubernetes namespace: ${NAMESPACE}"

# Check if namespace exists, create if not
kubectl get namespace ${NAMESPACE} &> /dev/null || {
    print_info "Creating namespace: ${NAMESPACE}"
    kubectl create namespace ${NAMESPACE}
}

# Apply the manifests
kubectl apply -f k8s-deployment.yaml -n ${NAMESPACE}

if [[ $? -eq 0 ]]; then
    print_status "Kubernetes manifests applied successfully"
else
    print_error "Kubernetes deployment failed"
    exit 1
fi

# Step 5: Wait for deployment to be ready
print_info "Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=120s deployment/ids-sync-service -n ${NAMESPACE}

if [[ $? -eq 0 ]]; then
    print_status "Deployment is ready!"
else
    print_warning "Deployment took longer than expected, but may still be starting"
fi

# Step 6: Display status
echo ""
print_info "Deployment Status:"
kubectl get deployment ids-sync-service -n ${NAMESPACE}

echo ""
print_info "Pod Status:"
kubectl get pods -l app=ids-sync-service -n ${NAMESPACE}

echo ""
print_info "Service Status:"
kubectl get service ids-sync-service -n ${NAMESPACE}

# Step 7: Show logs
echo ""
print_info "Recent logs (last 20 lines):"
kubectl logs -l app=ids-sync-service -n ${NAMESPACE} --tail=20

# Step 8: Provide useful commands
echo ""
print_status "Deployment Complete!"
echo ""
echo "📋 Useful Commands:"
echo "==================="
echo "View logs:           kubectl logs -f deployment/ids-sync-service -n ${NAMESPACE}"
echo "Check health:        kubectl exec deployment/ids-sync-service -n ${NAMESPACE} -- python healthcheck.py"
echo "Port forward:        kubectl port-forward service/ids-sync-service 8080:8080 -n ${NAMESPACE}"
echo "Scale deployment:    kubectl scale deployment ids-sync-service --replicas=1 -n ${NAMESPACE}"
echo "Update image:        kubectl set image deployment/ids-sync-service ids-sync=${IMAGE_NAME}:${IMAGE_TAG} -n ${NAMESPACE}"
echo "Delete deployment:   kubectl delete -f k8s-deployment.yaml -n ${NAMESPACE}"
echo ""
echo "🌐 Health Check URLs (after port-forward):"
echo "Health:              http://localhost:8080/health"
echo "Metrics:             http://localhost:8080/metrics"
echo ""
print_status "IDS Sync Service is now running in Kubernetes!"
echo "🔄 The service will automatically sync TextResources from Provider to Consumer"
echo "📊 Monitor the logs to see synchronization activity"