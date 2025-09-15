#!/bin/bash

# SDT Manager Build Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="sdt-manager"
TAG="${1:-latest}"

echo -e "${GREEN}Building SDT Manager Docker image...${NC}"

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

# Check if required files exist
check_files() {
    local required_files=("Dockerfile" "requirements.txt" "main.py")
    local missing_files=()
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            missing_files+=("$file")
        fi
    done
    
    if [ ${#missing_files[@]} -ne 0 ]; then
        print_error "Missing required files: ${missing_files[*]}"
        exit 1
    fi
    
    print_status "All required files found"
}

# Build Docker image
build_image() {
    print_status "Building Docker image: ${IMAGE_NAME}:${TAG}"
    print_status "This may take several minutes on first build..."
    
    # Build with proper context and error handling
    if docker build -t "${IMAGE_NAME}:${TAG}" .; then
        print_status "Docker image built successfully"
        
        # Show image size
        local image_size=$(docker images "${IMAGE_NAME}:${TAG}" --format "{{.Size}}")
        print_status "Image size: ${image_size}"
        
        return 0
    else
        print_error "Failed to build Docker image"
        return 1
    fi
}

# Clean up dangling images
cleanup_dangling() {
    print_status "Cleaning up dangling images..."
    local dangling_images=$(docker images -f "dangling=true" -q)
    
    if [ -n "$dangling_images" ]; then
        docker rmi $dangling_images 2>/dev/null || true
        print_status "Dangling images cleaned up"
    else
        print_status "No dangling images to clean up"
    fi
}

# Show build summary
show_summary() {
    print_status "Build Summary"
    echo "============="
    
    # Show the built image
    docker images "${IMAGE_NAME}:${TAG}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    
    echo ""
    print_status "Build completed successfully!"
    echo ""
    print_status "Next steps:"
    echo "  Deploy:  ./deploy.sh ${TAG}"
    echo "  Run:     docker run -d -p 8008:8008 ${IMAGE_NAME}:${TAG}"
    echo "  Test:    docker run --rm ${IMAGE_NAME}:${TAG} python3 -c \"import main; print('Import successful')\""
}

# Main execution
main() {
    print_status "SDT Manager Build Script"
    echo "========================"
    
    check_docker
    check_files
    
    if build_image; then
        cleanup_dangling
        show_summary
    else
        print_error "Build failed"
        exit 1
    fi
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "SDT Manager Build Script"
    echo ""
    echo "Usage: $0 [TAG]"
    echo ""
    echo "Arguments:"
    echo "  TAG    Docker image tag (default: latest)"
    echo ""
    echo "Prerequisites:"
    echo "  - Docker must be installed and running"
    echo "  - Dockerfile, requirements.txt, and main.py must exist"
    echo ""
    echo "Examples:"
    echo "  $0           # Build with 'latest' tag"
    echo "  $0 v1.0      # Build with 'v1.0' tag"
    echo "  $0 dev       # Build with 'dev' tag"
    echo ""
    exit 0
fi

# Run main function
main