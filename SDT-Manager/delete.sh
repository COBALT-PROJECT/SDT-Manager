#!/bin/bash
# Tear down the SDT-Manager pod and all associated Kubernetes resources.
#
# Run from the SDT-Manager/SDT-Manager/ directory:
#   ./delete.sh           # delete all resources, prompt before proceeding
#   ./delete.sh --force   # skip confirmation prompt

set -e

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------
NAMESPACE="default"
MANIFEST="../yaml_scripts/sdt-manager-k8s.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------
# Colors
# ---------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }

# ---------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------
FORCE=false
for arg in "$@"; do
    case $arg in
        --force|-f) FORCE=true ;;
        -h|--help)
            echo "Usage: ./delete.sh [--force]"
            echo ""
            echo "  --force   Skip confirmation prompt."
            exit 0
            ;;
        *) warn "Unknown argument: $arg" ;;
    esac
done

# ---------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------
echo "=================================================="
echo " SDT-Manager Deletion"
echo "=================================================="
echo ""

command -v kubectl &>/dev/null || error "kubectl is not installed or not in PATH."

if [[ ! -f "${SCRIPT_DIR}/${MANIFEST}" ]]; then
    error "Manifest not found at ${SCRIPT_DIR}/${MANIFEST}"
fi

# ---------------------------------------------------------------
# Show what will be deleted
# ---------------------------------------------------------------
info "Resources that will be removed:"
echo ""
echo "  Deployment:          sdt-manager-deployment"
echo "  Service:             sdt-manager-service"
echo "  PVC:                 sdt-manager-data-pvc"
echo "  ConfigMap:           sdt-manager-configmap"
echo "  ConfigMap:           sdt-manager-mqtt-config"
echo "  ConfigMap:           sdt-manager-yaml-scripts"
echo "  Secret:              sdt-manager-secret"
echo "  ClusterRoleBinding:  sdt-manager-rolebinding"
echo "  ClusterRole:         sdt-manager-role"
echo "  ServiceAccount:      sdt-manager-sa"
echo "  Namespace:           ${NAMESPACE}"
echo ""
warn "The PVC (sdt_credentials.db) will be deleted. Credentials will be lost."
echo ""

# ---------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------
if [[ "${FORCE}" == false ]]; then
    read -r -p "Are you sure you want to delete all SDT-Manager resources? [y/N] " confirm
    if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
        info "Deletion cancelled."
        exit 0
    fi
fi

echo ""

# ---------------------------------------------------------------
# Step 1: Delete Kubernetes resources
# ---------------------------------------------------------------
info "Step 1/3 -- Deleting Kubernetes resources..."
kubectl delete -f "${SCRIPT_DIR}/${MANIFEST}" -n "${NAMESPACE}" --ignore-not-found=true \
    || error "kubectl delete failed."
kubectl delete configmap sdt-manager-mqtt-config -n "${NAMESPACE}" --ignore-not-found=true \
    || error "Failed to delete MQTT ConfigMap."
success "Resources deleted."
echo ""

# ---------------------------------------------------------------
# Step 2: Wait for pod to terminate
# ---------------------------------------------------------------
info "Step 2/3 -- Waiting for pod to terminate..."
kubectl wait --for=delete pod -l app=sdt-manager -n "${NAMESPACE}" --timeout=60s 2>/dev/null \
    && success "Pod terminated." \
    || warn "Pod termination wait timed out (may already be gone)."
echo ""

# ---------------------------------------------------------------
# Step 3: Verify nothing remains
# ---------------------------------------------------------------
info "Step 3/3 -- Verifying cleanup..."

REMAINING=$(kubectl get all -l app=sdt-manager -n "${NAMESPACE}" 2>/dev/null | grep -v "^NAME" | grep -v "^$" || true)
if [[ -z "${REMAINING}" ]]; then
    success "All SDT-Manager resources have been removed."
else
    warn "Some resources may still be terminating:"
    echo "${REMAINING}"
fi

echo ""
echo "=================================================="
success "SDT-Manager deletion complete."
echo "=================================================="
echo ""
echo "To redeploy:  ./deploy.sh"
echo ""
