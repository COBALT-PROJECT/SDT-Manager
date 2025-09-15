#!/bin/bash

# SDT Manager Cleanup Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="sdt-manager"
IMAGE_NAME="sdt-manager"
COMPOSE_PROJECT_NAME="sdt-manager"

echo -e "${RED}Stopping and cleaning up SDT Manager...${NC}"

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

print_cleanup() {
    echo -e "${RED}[CLEANUP]${NC} $1"
}

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running."
        exit 1
    fi
}

# Stop and remove docker-compose deployment
cleanup_compose() {
    if command -v docker-compose &> /dev/null && [ -f "docker-compose.yml" ]; then
        print_cleanup "Stopping docker-compose deployment..."
        
        # Stop and remove containers, networks, volumes, and images created by up
        if docker-compose down --remove-orphans 2>/dev/null; then
            print_status "Docker-compose deployment stopped successfully"
            return 0
        else
            print_warning "Failed to stop docker-compose deployment or it wasn't running"
            return 1
        fi
    else
        print_warning "docker-compose not available or docker-compose.yml not found"
        return 1
    fi
}

# Stop and remove standalone container
cleanup_container() {
    print_cleanup "Checking for standalone container: ${CONTAINER_NAME}"
    
    # Check if container exists (running or stopped)
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        
        # Stop container if running
        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            print_cleanup "Stopping container: ${CONTAINER_NAME}"
            if docker stop "${CONTAINER_NAME}"; then
                print_status "Container stopped successfully"
            else
                print_error "Failed to stop container"
                return 1
            fi
        else
            print_status "Container was already stopped"
        fi
        
        # Remove container
        print_cleanup "Removing container: ${CONTAINER_NAME}"
        if docker rm "${CONTAINER_NAME}"; then
            print_status "Container removed successfully"
        else
            print_error "Failed to remove container"
            return 1
        fi
        
        return 0
    else
        print_warning "Container ${CONTAINER_NAME} not found"
        return 1
    fi
}

# Remove Docker image (optional)
cleanup_image() {
    local remove_image="$1"
    
    if [ "$remove_image" == "true" ]; then
        print_cleanup "Removing Docker images..."
        
        # Get all tags for the image
        local image_tags=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^${IMAGE_NAME}:" || true)
        
        if [ -n "$image_tags" ]; then
            print_cleanup "Found images: $image_tags"
            for tag in $image_tags; do
                print_cleanup "Removing image: $tag"
                if docker rmi "$tag" 2>/dev/null; then
                    print_status "Removed image: $tag"
                else
                    print_warning "Failed to remove image: $tag (may be in use)"
                fi
            done
        else
            print_warning "No ${IMAGE_NAME} images found"
        fi
    fi
}

# Clean up Docker volumes (optional)
cleanup_volumes() {
    local remove_volumes="$1"
    
    if [ "$remove_volumes" == "true" ]; then
        print_cleanup "Removing orphaned Docker volumes..."
        
        local orphaned_volumes=$(docker volume ls -q --filter dangling=true)
        if [ -n "$orphaned_volumes" ]; then
            print_cleanup "Found orphaned volumes, removing..."
            echo "$orphaned_volumes" | xargs docker volume rm 2>/dev/null || true
            print_status "Orphaned volumes cleaned up"
        else
            print_status "No orphaned volumes found"
        fi
    fi
}

# Clean up Docker networks (optional)
cleanup_networks() {
    local remove_networks="$1"
    
    if [ "$remove_networks" == "true" ]; then
        print_cleanup "Removing orphaned Docker networks..."
        
        # Remove networks created by docker-compose
        local compose_networks=$(docker network ls --format "{{.Name}}" | grep "${COMPOSE_PROJECT_NAME}" || true)
        if [ -n "$compose_networks" ]; then
            for network in $compose_networks; do
                print_cleanup "Removing network: $network"
                docker network rm "$network" 2>/dev/null || true
            done
        fi
        
        # Clean up orphaned networks
        docker network prune -f 2>/dev/null || true
        print_status "Network cleanup completed"
    fi
}

# Show cleanup summary
show_summary() {
    print_status "Cleanup Summary"
    echo "==============="
    
    # Check if any containers are still running
    local running_containers=$(docker ps --format "{{.Names}}" | grep "${CONTAINER_NAME}" || true)
    if [ -n "$running_containers" ]; then
        print_warning "Some containers are still running: $running_containers"
    else
        print_status "No SDT Manager containers running"
    fi
    
    # Check for remaining images
    local remaining_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^${IMAGE_NAME}:" || true)
    if [ -n "$remaining_images" ]; then
        print_status "Remaining images: $remaining_images"
    else
        print_status "No SDT Manager images remaining"
    fi
    
    echo ""
    print_status "Cleanup completed!"
}

# Parse command line arguments
REMOVE_IMAGE=false
REMOVE_VOLUMES=false
REMOVE_NETWORKS=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --remove-image)
            REMOVE_IMAGE=true
            shift
            ;;
        --remove-volumes)
            REMOVE_VOLUMES=true
            shift
            ;;
        --remove-networks)
            REMOVE_NETWORKS=true
            shift
            ;;
        --all)
            REMOVE_IMAGE=true
            REMOVE_VOLUMES=true
            REMOVE_NETWORKS=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "SDT Manager Cleanup Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --remove-image     Remove Docker images"
            echo "  --remove-volumes   Remove orphaned Docker volumes"
            echo "  --remove-networks  Remove Docker networks"
            echo "  --all              Remove everything (images, volumes, networks)"
            echo "  --force            Skip confirmation prompts"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                 # Stop and remove containers only"
            echo "  $0 --remove-image  # Also remove Docker images"
            echo "  $0 --all           # Remove everything"
            echo "  $0 --all --force   # Remove everything without confirmation"
            echo ""
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Confirmation prompt (unless --force is used)
if [ "$FORCE" != "true" ]; then
    echo ""
    print_warning "This will stop and remove SDT Manager containers."
    if [ "$REMOVE_IMAGE" == "true" ]; then
        print_warning "This will also remove Docker images."
    fi
    if [ "$REMOVE_VOLUMES" == "true" ]; then
        print_warning "This will also remove orphaned Docker volumes."
    fi
    if [ "$REMOVE_NETWORKS" == "true" ]; then
        print_warning "This will also remove Docker networks."
    fi
    echo ""
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Cleanup cancelled"
        exit 0
    fi
fi

# Main execution
main() {
    print_cleanup "SDT Manager Cleanup Script"
    echo "=========================="
    
    check_docker
    
    # Try to cleanup docker-compose first, then standalone container
    local cleanup_success=false
    
    if cleanup_compose; then
        cleanup_success=true
    fi
    
    if cleanup_container; then
        cleanup_success=true
    fi
    
    if [ "$cleanup_success" != "true" ]; then
        print_warning "No running SDT Manager deployments found to clean up"
    fi
    
    # Optional cleanups
    cleanup_image "$REMOVE_IMAGE"
    cleanup_volumes "$REMOVE_VOLUMES"
    cleanup_networks "$REMOVE_NETWORKS"
    
    show_summary
}

# Run main function
main