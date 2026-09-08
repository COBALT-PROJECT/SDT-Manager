#!/bin/bash
# Deploy the SDT-Manager pod into the k3s cluster.
# Assumes the image has already been built and imported via ./build.sh
#
# Usage:
#   ./deploy.sh

set -e

DEPLOYMENT_NAME="sdt-manager-deployment"
NAMESPACE="default"
MANIFEST="../yaml_scripts/sdt-manager-k8s.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }

echo "=================================================="
echo " SDT-Manager Pod Deployment"
echo "=================================================="
echo ""

# ---------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------
command -v kubectl &>/dev/null || error "kubectl is not installed or not in PATH."

[[ -f "${SCRIPT_DIR}/${MANIFEST}" ]] || error "Manifest not found at ${SCRIPT_DIR}/${MANIFEST}"

# ---------------------------------------------------------------
# Step 1: Apply manifests
# ---------------------------------------------------------------
info "Step 1/3 -- Applying Kubernetes manifests..."
kubectl apply -f "${SCRIPT_DIR}/${MANIFEST}" -n "${NAMESPACE}" || error "kubectl apply failed."
success "Manifests applied."
echo ""

# ---------------------------------------------------------------
# Step 2: Wait for rollout
# ---------------------------------------------------------------
info "Step 2/3 -- Waiting for deployment to become available (timeout: 120s)..."
if kubectl rollout status deployment/"${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --timeout=120s; then
    success "Deployment is ready."
else
    warn "Timed out waiting. Check pod status below for details."
fi
echo ""

# ---------------------------------------------------------------
# Step 3: Status
# ---------------------------------------------------------------
info "Step 3/3 -- Status:"
echo ""
echo "--- Pods ---"
kubectl get pods -l app=sdt-manager -n "${NAMESPACE}"
echo ""
echo "--- Service ---"
kubectl get service sdt-manager-service -n "${NAMESPACE}"
echo ""

POD=$(kubectl get pods -l app=sdt-manager -n "${NAMESPACE}" \
      -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -n "${POD}" ]]; then
    info "Recent logs from ${POD}:"
    kubectl logs "${POD}" -n "${NAMESPACE}" --tail=20 2>/dev/null || true
fi

echo ""
echo "=================================================="
success "Done."
echo "=================================================="
echo ""
echo "API (NodePort):   http://<node-ip>:30010"
echo "Within cluster:   http://sdt-manager-service:8008"
echo ""
echo "Useful commands:"
echo "  kubectl logs -f deployment/${DEPLOYMENT_NAME}"
echo "  kubectl get pods -l app=sdt-manager"
echo "  kubectl describe pod ${POD}"
echo ""
