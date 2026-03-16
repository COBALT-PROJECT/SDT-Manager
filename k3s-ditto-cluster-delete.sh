#!/bin/bash

# Ensure the script is run from the correct location
EXPECTED_DIR="/home/ubuntu/ditto"
if [ "$PWD" != "$EXPECTED_DIR" ]; then
    echo "Please run this script from the $EXPECTED_DIR directory."
    exit 1
fi

echo "Deleting all resources in the Ditto cluster..."

# Delete all ConfigMaps related to Ditto
echo "Deleting ConfigMaps..."
kubectl delete configmap nginx-conf nginx-cors nginx-htpasswd nginx-index swagger-ui-api --ignore-not-found

# Get all ConfigMap names and store them in an array
configmaps=$(kubectl get configmap --no-headers -o custom-columns=":metadata.name")

# Check if any ConfigMaps were found
if [ -z "$configmaps" ]; then
    echo "No ConfigMaps found"
    exit 0
fi

# Loop through each ConfigMap and delete it
for cm in $configmaps; do
    echo "Deleting ConfigMap: $cm"
    kubectl delete configmap "$cm"
done

echo "All ConfigMaps deleted successfully"

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
