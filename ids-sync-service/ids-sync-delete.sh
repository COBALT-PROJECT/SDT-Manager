#!/bin/bash

NAMESPACE="default"

echo "🗑️  Deleting IDS Sync Service resources from namespace: ${NAMESPACE}"

kubectl delete -f k8s-deployment.yaml -n ${NAMESPACE}
kubectl delete -f monitoring.yaml -n ${NAMESPACE}
kubectl delete service ids-sync-service -n ${NAMESPACE} --ignore-not-found
kubectl delete deployment ids-sync-service -n ${NAMESPACE} --ignore-not-found
kubectl delete configmap grafana-dashboard-ids-sync -n ${NAMESPACE} --ignore-not-found
kubectl delete servicemonitor ids-sync-service-monitor -n ${NAMESPACE} --ignore-not-found

echo "✅ All IDS Sync Service resources deleted (if they