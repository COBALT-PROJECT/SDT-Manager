#!/bin/bash

# SDT Manager Build and Deploy Script
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

echo -e "${GREEN}Starting SDT Manager containerization...${NC}"

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

# Check if kubectl is available (for Kubernetes access)
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_warning "kubectl is not installed. The container will include kubectl, but you may need it locally for testing."
    else
        print_status "kubectl is available locally"
    fi
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    mkdir -p yaml_scripts
    mkdir -p kubernetes
    mkdir -p logs
    
    # Create sample YAML files if they don't exist
    if [ ! -f "yaml_scripts/sdt-pod-with-ditto-k3s-itr2.yml" ]; then
        print_warning "YAML files not found. You'll need to provide the Kubernetes YAML files."
        echo "# Sample SDT Pod YAML - Replace with your actual file" > yaml_scripts/sdt-pod-with-ditto-k3s-itr2.yml
    fi
    
    if [ ! -f "yaml_scripts/sdt-service.yaml" ]; then
        echo "# Sample SDT Service YAML - Replace with your actual file" > yaml_scripts/sdt-service.yaml
    fi
}

# Build Docker image
build_image() {
    print_status "Building Docker image: ${IMAGE_NAME}:${TAG}"
    
    if docker build -t "${IMAGE_NAME}:${TAG}" .; then
        print_status "Docker image built successfully"
    else
        print_error "Failed to build Docker image"
        exit 1
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

# Run container with docker run (alternative to docker-compose)
run_container() {
    print_status "Starting SDT Manager container..."
    
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
        print_status "SDT Manager API is available at: http://localhost:8008"
        print_status "Check status at: http://localhost:8008/status"
        print_status "View logs with: docker logs -f ${CONTAINER_NAME}"
    else
        print_error "Failed to start container"
        exit 1
    fi
}

# Deploy with docker-compose (preferred method)
deploy_compose() {
    if command -v docker-compose &> /dev/null; then
        print_status "Deploying with docker-compose..."
        docker-compose down 2>/dev/null || true
        docker-compose up -d
        
        if [ $? -eq 0 ]; then
            print_status "Deployed successfully with docker-compose"
            print_status "SDT Manager API is available at: http://localhost:8008"
            print_status "Check logs with: docker-compose logs -f sdt-manager"
        else
            print_error "Failed to deploy with docker-compose"
            exit 1
        fi
    else
        print_warning "docker-compose not available, using docker run instead"
        cleanup_existing
        run_container
    fi
}

# Show status
show_status() {
    print_status "Container status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    print_status "Testing API endpoint..."
    sleep 3
    if curl -s http://localhost:8008/status > /dev/null; then
        print_status "API is responding correctly"
    else
        print_warning "API might still be starting up. Check logs with: docker logs ${CONTAINER_NAME}"
    fi
}

# Main execution
main() {
    print_status "SDT Manager Containerization Script"
    echo "======================================"
    
    check_docker
    check_kubectl
    create_directories
    build_image
    deploy_compose
    show_status
    
    echo ""
    print_status "Deployment complete!"
    echo -e "${GREEN}Access your SDT Manager at: http://localhost:8008${NC}"
    echo -e "${GREEN}API Documentation: http://localhost:8008/docs${NC}"
    echo ""
    echo "Useful commands:"
    echo "  - View logs: docker logs -f ${CONTAINER_NAME}"
    echo "  - Stop container: docker stop ${CONTAINER_NAME}"
    echo "  - Restart container: docker restart ${CONTAINER_NAME}"
    echo "  - Remove container: docker rm -f ${CONTAINER_NAME}"
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "SDT Manager Build and Deploy Script"
    echo ""
    echo "Usage: $0 [TAG]"
    echo ""
    echo "Arguments:"
    echo "  TAG    Docker image tag (default: latest)"
    echo ""
    echo "Examples:"
    echo "  $0           # Build with 'latest' tag"
    echo "  $0 v1.0      # Build with 'v1.0' tag"
    echo ""
    exit 0
fi

# Run main function
main