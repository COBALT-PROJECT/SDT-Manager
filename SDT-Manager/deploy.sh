#!/bin/bash
# Deploy the SDT-Manager (quantum) pod into the k3s cluster.
# Assumes the image has already been built and imported via ./build.sh
#
# Usage:
#   ./deploy.sh

set -euo pipefail

DEPLOYMENT_NAME="sdt-manager-quantum-deployment"
NAMESPACE="default"
MANIFEST="../yaml_scripts/sdt-manager-quantum-k8s.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }

env_value() {
    local key="$1"
    sed -n "s/^${key}=//p" "${ENV_FILE}" | tail -n 1 | tr -d '\r'
}

echo "=================================================="
echo " SDT-Manager Quantum Pod Deployment"
echo "=================================================="
echo ""

# ---------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------
command -v kubectl &>/dev/null || error "kubectl is not installed or not in PATH."

[[ -f "${SCRIPT_DIR}/${MANIFEST}" ]] || error "Manifest not found at ${SCRIPT_DIR}/${MANIFEST}"
[[ -f "${ENV_FILE}" ]] || error "Environment file not found at ${ENV_FILE}"

MQTT_FAILURE_REPORTING_ENABLED="$(env_value MQTT_FAILURE_REPORTING_ENABLED)"
MQTT_FAILURE_HOST="$(env_value MQTT_FAILURE_HOST)"
MQTT_FAILURE_PORT="$(env_value MQTT_FAILURE_PORT)"
MQTT_COMPONENT_ID="$(env_value MQTT_COMPONENT_ID)"
MQTT_FAILURE_QUEUE_SIZE="$(env_value MQTT_FAILURE_QUEUE_SIZE)"
MQTT_FAILURE_MAX_RETRIES="$(env_value MQTT_FAILURE_MAX_RETRIES)"
MQTT_FAILURE_RETRY_DELAY="$(env_value MQTT_FAILURE_RETRY_DELAY)"

[[ -n "${MQTT_FAILURE_HOST}" ]] || error "MQTT_FAILURE_HOST is missing from ${ENV_FILE}"
[[ "${MQTT_FAILURE_PORT}" =~ ^[0-9]+$ ]] || error "MQTT_FAILURE_PORT must be numeric"
[[ -n "${MQTT_COMPONENT_ID}" ]] || error "MQTT_COMPONENT_ID is missing from ${ENV_FILE}"

info "Importing MQTT settings from ${ENV_FILE}..."
kubectl create configmap sdt-manager-quantum-mqtt-config \
    --namespace "${NAMESPACE}" \
    --from-literal=MQTT_FAILURE_REPORTING_ENABLED="${MQTT_FAILURE_REPORTING_ENABLED}" \
    --from-literal=MQTT_FAILURE_HOST="${MQTT_FAILURE_HOST}" \
    --from-literal=MQTT_FAILURE_PORT="${MQTT_FAILURE_PORT}" \
    --from-literal=MQTT_COMPONENT_ID="${MQTT_COMPONENT_ID}" \
    --from-literal=MQTT_FAILURE_QUEUE_SIZE="${MQTT_FAILURE_QUEUE_SIZE}" \
    --from-literal=MQTT_FAILURE_MAX_RETRIES="${MQTT_FAILURE_MAX_RETRIES}" \
    --from-literal=MQTT_FAILURE_RETRY_DELAY="${MQTT_FAILURE_RETRY_DELAY}" \
    --dry-run=client -o yaml | kubectl apply -f -
success "MQTT configuration imported from .env."
echo ""

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
kubectl get pods -l app=sdt-manager-quantum -n "${NAMESPACE}"
echo ""
echo "--- Service ---"
kubectl get service sdt-manager-quantum-service -n "${NAMESPACE}"
echo ""

POD=$(kubectl get pods -l app=sdt-manager-quantum -n "${NAMESPACE}" \
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
echo "API (NodePort):   http://<node-ip>:30011"
echo "Within cluster:   http://sdt-manager-quantum-service:8008"
echo ""
echo "Useful commands:"
echo "  kubectl logs -f deployment/${DEPLOYMENT_NAME}"
echo "  kubectl get pods -l app=sdt-manager-quantum"
echo "  kubectl describe pod ${POD}"
echo ""
