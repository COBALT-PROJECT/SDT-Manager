#!/bin/bash

# SDT Manager Deploy Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="sdt-manager"
TAG="${1:-latest}"
CONTAINER_NAME="sdt-manager"

echo -e "${GREEN}Deploying SDT Manager...${NC}"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed and running
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    print_status "Docker is available and running"
}

# Check if image exists
check_image() {
    if ! docker image inspect "${IMAGE_NAME}:${TAG}" &> /dev/null; then
        print_error "Docker image ${IMAGE_NAME}:${TAG} not found."
        print_error "Please build the image first using: docker build -t ${IMAGE_NAME}:${TAG} ."
        exit 1
    fi
    print_status "Docker image ${IMAGE_NAME}:${TAG} found"
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    mkdir -p yaml_scripts
    mkdir -p kubernetes
    mkdir -p logs
    
    # Create sample YAML files if they don't exist
    if [ ! -f "yaml_scripts/sdt-pod-with-ditto-k3s-itr2.yml" ]; then
        print_warning "YAML files not found in yaml_scripts/. You'll need to provide the Kubernetes YAML files."
    fi
    
    if [ ! -f "kubernetes/ca-pemstore.yaml" ]; then
        print_warning "IDS connector files not found in kubernetes/. You'll need to provide the IDS connector YAML files."
    fi
}

# Stop and remove existing container
cleanup_existing() {
    if docker ps -a --format 'table {{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        print_status "Stopping and removing existing container: ${CONTAINER_NAME}"
        docker stop "${CONTAINER_NAME}" 2>/dev/null || true
        docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    fi
}

# Deploy with docker-compose (preferred method)
deploy_compose() {
    if command -v docker-compose &> /dev/null && [ -f "docker-compose.yml" ]; then
        print_status "Deploying with docker-compose..."
        docker-compose down 2>/dev/null || true
        docker-compose up -d
        
        if [ $? -eq 0 ]; then
            print_status "Deployed successfully with docker-compose"
            return 0
        else
            print_error "Failed to deploy with docker-compose"
            return 1
        fi
    else
        return 1
    fi
}

# Run container with docker run (fallback method)
run_container() {
    print_status "Starting SDT Manager container with docker run..."
    
    # Check if kubeconfig exists
    if [ ! -d "${HOME}/.kube" ] || [ ! -f "${HOME}/.kube/config" ]; then
        print_warning "Kubernetes config not found at ${HOME}/.kube/config"
        print_warning "Container will start but kubectl commands may not work"
    fi
    
    docker run -d \
        --name "${CONTAINER_NAME}" \
        -p 8008:8008 \
        -e SDT_INTERFACE_HOST=localhost \
        -e SDT_INTERFACE_PORT=30008 \
        -e API_SERVER_HOST=0.0.0.0 \
        -e API_SERVER_PORT=8008 \
        -v "${HOME}/.kube/config:/home/sdt/.kube/config:ro" \
        -v "$(pwd)/yaml_scripts:/home/ubuntu/k3s-SDT-Ditto/yaml_scripts:ro" \
        -v "$(pwd)/kubernetes:/home/ubuntu/true-connector/kubernetes:ro" \
        -v "$(pwd)/logs:/app/logs" \
        --restart unless-stopped \
        "${IMAGE_NAME}:${TAG}"
    
    if [ $? -eq 0 ]; then
        print_status "Container started successfully"
        return 0
    else
        print_error "Failed to start container"
        return 1
    fi
}

# Wait for container to be healthy
wait_for_health() {
    print_status "Waiting for container to be healthy..."
    
    for i in {1..30}; do
        if docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
            sleep 2
            if curl -s http://localhost:8008/status > /dev/null 2>&1; then
                print_status "Container is healthy and responding"
                return 0
            fi
        fi
        
        if [ $i -eq 30 ]; then
            print_warning "Container may still be starting up"
            return 1
        fi
        
        sleep 2
    done
}

# Show status and useful information
show_status() {
    print_status "Deployment completed!"
    echo ""
    
    print_status "Container status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    print_status "Application URLs:"
    echo -e "  ${GREEN}API:${NC} http://localhost:8008"
    echo -e "  ${GREEN}Status:${NC} http://localhost:8008/status"
    echo -e "  ${GREEN}Documentation:${NC} http://localhost:8008/docs"
    
    echo ""
    print_status "Useful commands:"
    echo "  View logs:      docker logs -f ${CONTAINER_NAME}"
    echo "  Stop container: docker stop ${CONTAINER_NAME}"
    echo "  Restart:        docker restart ${CONTAINER_NAME}"
    echo "  Shell access:   docker exec -it ${CONTAINER_NAME} /bin/bash"
    echo "  Stop and clean: ./cleanup.sh"
}

# Main execution
main() {
    print_status "SDT Manager Deployment Script"
    echo "============================="
    
    check_docker
    check_image
    create_directories
    cleanup_existing
    
    # Try docker-compose first, fallback to docker run
    if ! deploy_compose; then
        print_warning "docker-compose not available or failed, using docker run instead"
        if ! run_container; then
            print_error "Deployment failed"
            exit 1
        fi
    fi
    
    wait_for_health
    show_status
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "SDT Manager Deploy Script"
    echo ""
    echo "Usage: $0 [TAG]"
    echo ""
    echo "Arguments:"
    echo "  TAG    Docker image tag (default: latest)"
    echo ""
    echo "Prerequisites:"
    echo "  - Docker image must be built first"
    echo "  - Docker must be running"
    echo "  - YAML files should be in yaml_scripts/ and kubernetes/ directories"
    echo ""
    echo "Examples:"
    echo "  $0           # Deploy with 'latest' tag"
    echo "  $0 v1.0      # Deploy with 'v1.0' tag"
    echo ""
    exit 0
fi

# Run main function
main