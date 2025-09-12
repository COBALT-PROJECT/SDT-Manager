#!/bin/bash

# Test IDS Sync Service Deployment
# Usage: ./test-deployment.sh

set -e

NAMESPACE="default"
SERVICE_NAME="ids-sync-service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

echo "🧪 Testing IDS Sync Service Deployment"
echo "======================================"

# Test 1: Check if deployment exists and is ready
print_info "Test 1: Checking deployment status..."
if kubectl get deployment ${SERVICE_NAME} -n ${NAMESPACE} &> /dev/null; then
    READY_REPLICAS=$(kubectl get deployment ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.status.readyReplicas}')
    REPLICAS=$(kubectl get deployment ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.replicas}')
    
    if [[ "${READY_REPLICAS}" == "${REPLICAS}" ]]; then
        print_status "Deployment is ready (${READY_REPLICAS}/${REPLICAS})"
    else
        print_error "Deployment not ready (${READY_REPLICAS:-0}/${REPLICAS})"
        exit 1
    fi
else
    print_error "Deployment not found"
    exit 1
fi

# Test 2: Check pod status
print_info "Test 2: Checking pod status..."
POD_NAME=$(kubectl get pods -l app=${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -n "${POD_NAME}" ]]; then
    POD_STATUS=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.phase}')
    if [[ "${POD_STATUS}" == "Running" ]]; then
        print_status "Pod is running: ${POD_NAME}"
    else
        print_error "Pod status: ${POD_STATUS}"
        kubectl describe pod ${POD_NAME} -n ${NAMESPACE}
        exit 1
    fi
else
    print_error "No pods found"
    exit 1
fi

# Test 3: Check service
print_info "Test 3: Checking service..."
if kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} &> /dev/null; then
    CLUSTER_IP=$(kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
    PORT=$(kubectl get service ${SERVICE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.ports[0].port}')
    print_status "Service available at ${CLUSTER_IP}:${PORT}"
else
    print_error "Service not found"
    exit 1
fi

# Test 4: Health check
print_info "Test 4: Testing health endpoint..."
HEALTH_RESPONSE=$(kubectl exec ${POD_NAME} -n ${NAMESPACE} -- curl -s http://localhost:8080/health 2>/dev/null || echo "failed")

if [[ "${HEALTH_RESPONSE}" != "failed" ]]; then
    echo "${HEALTH_RESPONSE}" | grep -q "healthy\|starting" && {
        print_status "Health check passed"
    } || {
        print_warning "Health check response: ${HEALTH_RESPONSE}"
    }
else
    print_error "Health check failed"
fi

# Test 5: Check logs for errors
print_info "Test 5: Checking recent logs for errors..."
ERROR_COUNT=$(kubectl logs ${POD_NAME} -n ${NAMESPACE} --tail=50 | grep -c "ERROR\|❌" || echo "0")

if [[ "${ERROR_COUNT}" -eq 0 ]]; then
    print_status "No errors found in recent logs"
else
    print_warning "Found ${ERROR_COUNT} errors in recent logs"
    echo "Recent error logs:"
    kubectl logs ${POD_NAME} -n ${NAMESPACE} --tail=20 | grep "ERROR\|❌" || true
fi

# Test 6: Test metrics endpoint
print_info "Test 6: Testing metrics endpoint..."
METRICS_RESPONSE=$(kubectl exec ${POD_NAME} -n ${NAMESPACE} -- curl -s http://localhost:8080/metrics 2>/dev/null || echo "failed")

if [[ "${METRICS_RESPONSE}" != "failed" ]] && echo "${METRICS_RESPONSE}" | grep -q "ids_sync"; then
    print_status "Metrics endpoint working"
    echo "Available metrics:"
    echo "${METRICS_RESPONSE}" | grep "# HELP" | head -5
else
    print_warning "Metrics endpoint issue"
fi

# Test 7: Check environment variables
print_info "Test 7: Checking environment configuration..."
PROVIDER_URL=$(kubectl exec ${POD_NAME} -n ${NAMESPACE} -- printenv PROVIDER_URL 2>/dev/null || echo "not set")
CONSUMER_URL=$(kubectl exec ${POD_NAME} -n ${NAMESPACE} -- printenv CONSUMER_URL 2>/dev/null || echo "not set")

echo "   Provider URL: ${PROVIDER_URL}"
echo "   Consumer URL: ${CONSUMER_URL}"

if [[ "${PROVIDER_URL}" != "not set" ]] && [[ "${CONSUMER_URL}" != "not set" ]]; then
    print_status "Environment variables configured"
else
    print_warning "Some environment variables missing"
fi

# Test 8: Port forward test
print_info "Test 8: Testing port forwarding capability..."
echo "Starting port forward test (10 seconds)..."

# Start port forward in background
kubectl port-forward service/${SERVICE_NAME} 8080:8080 -n ${NAMESPACE} &
PF_PID=$!

# Wait a moment for port forward to establish
sleep 3

# Test the forwarded port
if curl -s http://localhost:8080/health &> /dev/null; then
    print_status "Port forwarding works"
else
    print_warning "Port forwarding test failed (service may still be starting)"
fi

# Clean up port forward
kill $PF_PID 2>/dev/null || true
wait $PF_PID 2>/dev/null || true

# Summary
echo ""
print_status "Deployment Test Complete!"
echo ""
echo "📊 Summary:"
echo "==========="
kubectl get all -l app=${SERVICE_NAME} -n ${NAMESPACE}

echo ""
echo "🔧 Quick Commands:"
echo "=================="
echo "View logs:       kubectl logs -f deployment/${SERVICE_NAME} -n ${NAMESPACE}"
echo "Exec into pod:   kubectl exec -it ${POD_NAME} -n ${NAMESPACE} -- /bin/bash"
echo "Port forward:    kubectl port-forward service/${SERVICE_NAME} 8080:8080 -n ${NAMESPACE}"
echo "Check health:    curl http://localhost:8080/health (after port forward)"
echo "View metrics:    curl http://localhost:8080/metrics (after port forward)"
echo ""
print_info "Service is ready to synchronize IDS resources!"