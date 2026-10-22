#!/usr/bin/env bash
# Usage: ./build.sh [tag]; SKIP_K3S_IMPORT=1 ./build.sh [tag] builds only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${1:-latest}"
if [[ $# -gt 1 || ! "$TAG" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ ]]; then
    echo "Usage: $0 [valid-image-tag]" >&2
    exit 2
fi
IMAGE="sdt-manager-timestamps:${TAG}"
command -v docker >/dev/null
docker build --tag "$IMAGE" "$SCRIPT_DIR"
if [[ "${SKIP_K3S_IMPORT:-0}" != 1 ]]; then
    command -v k3s >/dev/null
    ARCHIVE="$(mktemp /tmp/sdt-manager-timestamps.XXXXXXXX.tar)"
    trap 'rm -f -- "$ARCHIVE"' EXIT
    docker save --output "$ARCHIVE" "$IMAGE"
    # Import replaces the tagged image without deleting a running image first.
    if [[ $EUID -eq 0 ]]; then
        k3s ctr images import "$ARCHIVE"
    else
        sudo k3s ctr images import "$ARCHIVE"
    fi
fi
echo "Built $IMAGE. Deploy with: ${SCRIPT_DIR}/deploy.sh $TAG"
