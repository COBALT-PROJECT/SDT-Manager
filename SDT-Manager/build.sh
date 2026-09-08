#!/bin/bash
# Build the sdt-manager Docker image and import it into k3s containerd.
# If the same tag already exists in k3s it is removed first.
#
# Usage:
#   ./build.sh           # tag: sdt-manager:latest
#   ./build.sh 0.0.2     # tag: sdt-manager:0.0.2

set -e

TAG="${1:-latest}"
IMAGE="sdt-manager:${TAG}"
TMP_TAR="/tmp/sdt-manager-image.tar"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }

# ---------------------------------------------------------------
# Step 1: Build
# ---------------------------------------------------------------
info "Step 1/3 -- Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" . || error "Docker build failed."
success "Image built: ${IMAGE}"
echo ""

# ---------------------------------------------------------------
# Step 2: Remove existing image from k3s if present
# k3s stores locally imported images as docker.io/library/<name>:<tag>
# ---------------------------------------------------------------
K3S_REF="docker.io/library/${IMAGE}"
info "Step 2/3 -- Checking k3s containerd for existing image..."
if sudo k3s ctr images list | grep -q "${K3S_REF}"; then
    info "Found existing image in k3s — removing it..."
    sudo k3s ctr images rm "${K3S_REF}" || true
    success "Old image removed."
else
    info "No existing image found in k3s — clean import."
fi
echo ""

# ---------------------------------------------------------------
# Step 3: Import new image into k3s
# ---------------------------------------------------------------
info "Step 3/3 -- Importing image into k3s containerd..."
docker save "${IMAGE}" > "${TMP_TAR}" || error "Failed to save image to ${TMP_TAR}."
sudo k3s ctr images import "${TMP_TAR}" || error "Failed to import image into k3s."
rm -f "${TMP_TAR}"
success "Image imported into k3s: ${IMAGE}"
echo ""

echo "=================================================="
success "Build complete. Image ${IMAGE} is ready in k3s."
echo "=================================================="
echo ""
echo "Next step:  ./deploy.sh"
echo ""
