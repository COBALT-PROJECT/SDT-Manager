#!/bin/bash

# Deploy-only script for IDS Sync Service

set -e

IMAGE_NAME="ids-sync-service"
IMAGE_TAG="latest"
NAMESPACE="default"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✅ $1${NC}"; }
print_info()   { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_warning(){ echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()  { echo -e "${RED}❌ $1${NC}"; }

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

print_info "Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=120s deployment/ids-sync-service -n ${NAMESPACE}

if [[ $? -eq 0 ]]; then
    print_status "Deployment is ready!"
else
    print_warning "Deployment took longer than expected, but may still be starting"
fi

echo ""
print_info "Deployment Status:"
kubectl get deployment ids-sync-service -n ${NAMESPACE}

echo ""
print_info "Pod Status:"
kubectl get pods -l app=ids-sync-service -n ${NAMESPACE}

echo ""
print_info "Service Status:"
kubectl get service ids-sync-service -n ${NAMESPACE}

echo ""
print_status