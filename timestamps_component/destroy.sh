#!/usr/bin/env bash
# Remove only the timestamp manager. Preserve its data unless explicitly purged.
set -euo pipefail
PURGE_DATA=0
if [[ $# == 1 && "$1" == --purge-data ]]; then
    PURGE_DATA=1
elif [[ $# != 0 ]]; then
    echo "Usage: $0 [--purge-data]" >&2
    exit 2
fi
command -v kubectl >/dev/null
kubectl delete --namespace default --ignore-not-found --wait=true \
    deployment/sdt-manager-timestamps-deployment \
    service/sdt-manager-timestamps-service
kubectl delete --namespace default --ignore-not-found \
    configmap/sdt-manager-timestamps-configmap \
    configmap/sdt-manager-timestamps-yaml-scripts \
    secret/sdt-manager-timestamps-secret \
    serviceaccount/sdt-manager-timestamps-sa
kubectl delete --ignore-not-found \
    clusterrolebinding/sdt-manager-timestamps-rolebinding \
    clusterrole/sdt-manager-timestamps-role
if [[ $PURGE_DATA == 1 ]]; then
    kubectl delete pvc/sdt-manager-timestamps-data-pvc \
        --namespace default --ignore-not-found
    echo "Timestamp data PVC deleted; credentials and timing archive may be unrecoverable."
else
    echo "Timestamp manager removed. Its data PVC and timing archive were retained."
fi
echo "Shared SDT/IDS resources and the quantum manager were left in place."
