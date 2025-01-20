#!/bin/bash

# Ensure the script is run from the correct location
EXPECTED_DIR="/home/allen/ditto"
if [ "$PWD" != "$EXPECTED_DIR" ]; then
    echo "Please run this script from the $EXPECTED_DIR directory."
    exit 1
fi

echo "Deleting all resources in the Ditto cluster..."

# Delete all ConfigMaps related to Ditto
echo "Deleting ConfigMaps..."
kubectl delete configmap nginx-conf nginx-cors nginx-htpasswd nginx-index swagger-ui-api --ignore-not-found

# Delete MongoDB deployment and service
echo "Deleting MongoDB resources..."
kubectl delete -f deployment/kubernetes/deploymentFiles/mongodb/mongodb.yaml --ignore-not-found

# Delete Ditto log files pod
echo "Deleting Ditto log files pod..."
kubectl delete -f deployment/kubernetes/deploymentFiles/ditto/ditto-log-files.yaml --ignore-not-found

# Delete Ditto core services
echo "Deleting Ditto core services..."
kubectl delete -f deployment/kubernetes/deploymentFiles/ditto/ --ignore-not-found

# Delete Swagger UI deployment and service
echo "Deleting Swagger UI resources..."
kubectl delete -f deployment/kubernetes/deploymentFiles/swagger/swagger.yaml --ignore-not-found

# Delete Nginx deployment and service
echo "Deleting Nginx resources..."
kubectl delete -f deployment/kubernetes/deploymentFiles/nginx/nginx.yaml --ignore-not-found

# Delete all pods, deployments, services, and other resources in the default namespace (optional)
echo "Deleting all remaining resources in the default namespace..."
kubectl delete all --all -n default --ignore-not-found

# Confirm deletion
echo "Checking for remaining resources in the default namespace..."
kubectl get all -n default

echo "Ditto cluster cleanup completed."
