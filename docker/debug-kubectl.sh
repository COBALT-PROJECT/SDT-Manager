#!/bin/bash

# Debug script for kubectl configuration issues
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[DEBUG]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

CONTAINER_NAME="sdt-manager"

echo "Debugging kubectl configuration in SDT Manager container..."
echo "=========================================================="

# Check if container is running
if ! docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    print_error "Container ${CONTAINER_NAME} is not running"
    exit 1
fi

print_status "Container is running"

# Check host kubeconfig
echo ""
print_status "Host kubeconfig status:"
if [ -f "$HOME/.kube/config" ]; then
    echo "  ✓ File exists: $HOME/.kube/config"
    echo "  ✓ Size: $(stat -c%s "$HOME/.kube/config") bytes"
    echo "  ✓ Permissions: $(stat -c%A "$HOME/.kube/config")"
else
    print_error "Host kubeconfig not found at $HOME/.kube/config"
    exit 1
fi

# Check container's .kube directory
echo ""
print_status "Container .kube directory:"
docker exec "$CONTAINER_NAME" ls -la /home/sdt/.kube/ || print_error "Could not list .kube directory"

# Check if config is a file or directory in container
echo ""
print_status "Container config file type:"
docker exec "$CONTAINER_NAME" file /home/sdt/.kube/config || print_error "Could not check config file type"

# Check container config permissions
echo ""
print_status "Container config permissions:"
docker exec "$CONTAINER_NAME" stat /home/sdt/.kube/config || print_error "Could not stat config file"

# Check if kubectl works in container
echo ""
print_status "Testing kubectl in container:"
docker exec "$CONTAINER_NAME" kubectl version --client || print_error "kubectl not working"

# Check KUBECONFIG environment variable
echo ""
print_status "KUBECONFIG environment variable:"
docker exec "$CONTAINER_NAME" printenv | grep -i kube || echo "No KUBE environment variables set"

# Test kubectl config view
echo ""
print_status "Testing kubectl config view:"
docker exec "$CONTAINER_NAME" kubectl config view || print_error "kubectl config view failed"

# Show suggested fixes
echo ""
print_status "Suggested fixes:"
echo "1. Stop and remove container: docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME"
echo "2. Run with explicit config file mount:"
echo "   docker run -d --name $CONTAINER_NAME -p 8008:8008 \\"
echo "     -v '$HOME/.kube/config:/home/sdt/.kube/config:ro' \\"
echo "     -v '$(pwd)/yaml_scripts:/home/ubuntu/k3s-SDT-Ditto/yaml_scripts:ro' \\"
echo "     -v '$(pwd)/kubernetes:/home/ubuntu/true-connector/kubernetes:ro' \\"
echo "     -v '$(pwd)/logs:/app/logs' \\"
echo "     sdt-manager:latest"
echo ""
echo "3. Alternative: Copy config into container:"
echo "   docker cp '$HOME/.kube/config' $CONTAINER_NAME:/home/sdt/.kube/config"
echo "   docker exec $CONTAINER_NAME chown sdt:sdt /home/sdt/.kube/config"