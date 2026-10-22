#!/usr/bin/env bash
# Usage: ./deploy.sh [tag] [--dry-run]; NODE_PORT=30012 ENV_FILE=/path/.env ...
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG=latest
DRY_RUN=0
TAG_SET=0
for arg in "$@"; do
    if [[ "$arg" == --dry-run ]]; then
        DRY_RUN=1
    elif [[ "$arg" != --* && $TAG_SET == 0 ]]; then
        TAG="$arg"
        TAG_SET=1
    else
        echo "Usage: $0 [tag] [--dry-run]" >&2
        exit 2
    fi
done
NODE_PORT="${NODE_PORT:-30012}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
MANIFEST="$(python3 "${SCRIPT_DIR}/render_manifest.py" --tag "$TAG" --node-port "$NODE_PORT")"
if [[ $DRY_RUN == 1 ]]; then
    printf '%s\n' "$MANIFEST"
    exit 0
fi
command -v kubectl >/dev/null
[[ -f "$ENV_FILE" ]] || { echo "Missing environment file: $ENV_FILE" >&2; exit 1; }
# Values are read as data, never sourced as shell code. Runtime cluster paths in
# the ConfigMap override local paths from this Secret.
kubectl create secret generic sdt-manager-timestamps-secret \
    --namespace default --from-env-file="$ENV_FILE" --dry-run=client -o yaml |
    kubectl apply -f -
printf '%s\n' "$MANIFEST" | kubectl apply --namespace default -f -
kubectl rollout status deployment/sdt-manager-timestamps-deployment \
    --namespace default --timeout=180s
kubectl get pods,service --namespace default -l app=sdt-manager-timestamps
echo "Timestamp API: http://<node-ip>:${NODE_PORT}"
echo "Timing records: /api/SDTM/performance; summary: /api/SDTM/performance/summary"
