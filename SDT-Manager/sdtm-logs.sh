#!/usr/bin/env bash

set -euo pipefail

DEPLOYMENT="${SDTM_DEPLOYMENT:-sdt-manager-quantum-deployment}"
NAMESPACE="${SDTM_NAMESPACE:-default}"
TAIL_LINES="${1:-0}"

if ! [[ "${TAIL_LINES}" =~ ^[0-9]+$ ]]; then
    echo "Usage: $0 [number-of-previous-lines]" >&2
    exit 2
fi

command -v kubectl >/dev/null 2>&1 || {
    echo "Error: kubectl is not installed or not in PATH." >&2
    exit 1
}

echo "Following ${DEPLOYMENT} logs in namespace ${NAMESPACE}."
echo "Hiding /health and /ready requests. Press Ctrl+C to stop."

kubectl logs \
    --follow \
    --namespace "${NAMESPACE}" \
    --tail="${TAIL_LINES}" \
    "deployment/${DEPLOYMENT}" \
    | grep --line-buffered -vE '"GET /(health|ready) HTTP'
