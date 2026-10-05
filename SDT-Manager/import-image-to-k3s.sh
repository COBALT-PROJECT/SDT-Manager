#!/usr/bin/env bash
# Import the locally built SDT Manager image into k3s containerd.
# If the same image reference already exists in k3s, replace it.
#
# Usage:
#   ./import-image-to-k3s.sh          # sdt-manager:latest
#   ./import-image-to-k3s.sh 0.0.2    # sdt-manager:0.0.2

set -Eeuo pipefail

TAG="${1:-latest}"
LOCAL_IMAGE="sdt-manager:${TAG}"
K3S_IMAGE="docker.io/library/${LOCAL_IMAGE}"
IMAGE_ARCHIVE=""

info() {
    printf '[INFO]  %s\n' "$*"
}

success() {
    printf '[OK]    %s\n' "$*"
}

error() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${IMAGE_ARCHIVE}" && -f "${IMAGE_ARCHIVE}" ]]; then
        rm -f -- "${IMAGE_ARCHIVE}"
        info "Deleted temporary archive ${IMAGE_ARCHIVE}."
    fi
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || error "docker is not installed or not in PATH."
command -v k3s >/dev/null 2>&1 || error "k3s is not installed or not in PATH."
command -v sudo >/dev/null 2>&1 || error "sudo is not installed or not in PATH."

docker image inspect "${LOCAL_IMAGE}" >/dev/null 2>&1 || \
    error "Local Docker image ${LOCAL_IMAGE} does not exist. Build it first."

# Authenticate once before running any k3s containerd commands.
sudo -v

info "Checking k3s containerd for ${K3S_IMAGE}..."
if sudo k3s ctr images list -q | grep -Fqx -- "${K3S_IMAGE}"; then
    IMAGE_EXISTS=true
    info "The image already exists in k3s and will be replaced."
else
    IMAGE_EXISTS=false
    info "The image is not present in k3s and will be imported."
fi

# Export before removing the old k3s image. If the export fails, the existing
# image remains available to running or future pods.
IMAGE_ARCHIVE="$(mktemp /tmp/sdt-manager-image.XXXXXX.tar)"
info "Exporting ${LOCAL_IMAGE} to a temporary archive..."
docker save --output "${IMAGE_ARCHIVE}" "${LOCAL_IMAGE}"

if [[ "${IMAGE_EXISTS}" == true ]]; then
    info "Removing existing k3s image ${K3S_IMAGE}..."
    sudo k3s ctr images remove "${K3S_IMAGE}"
fi

info "Importing ${LOCAL_IMAGE} into k3s containerd..."
sudo k3s ctr images import "${IMAGE_ARCHIVE}"

if ! sudo k3s ctr images list -q | grep -Fqx -- "${K3S_IMAGE}"; then
    error "Import finished, but ${K3S_IMAGE} was not found in k3s containerd."
fi

success "${K3S_IMAGE} is available in k3s containerd."
