#!/bin/bash

# Create ConfigMaps
echo "Creating ConfigMaps..."
kubectl create configmap nginx-conf --from-file=deployment/kubernetes/deploymentFiles/nginx/nginx.conf
kubectl create configmap nginx-cors --from-file=deployment/kubernetes/deploymentFiles/nginx/nginx-cors.conf
kubectl create configmap nginx-htpasswd --from-file=deployment/kubernetes/deploymentFiles/nginx/nginx.htpasswd
kubectl create configmap nginx-index --from-file=deployment/kubernetes/deploymentFiles/nginx/index.html
kubectl create configmap swagger-ui-api --from-file=$PWD/documentation/src/main/resources/openapi

# Apply MongoDB deployment
echo "Deploying MongoDB..."
kubectl apply -f deployment/kubernetes/deploymentFiles/mongodb/mongodb.yaml

# Apply Ditto log files deployment
echo "Deploying Ditto log files..."
kubectl apply -f deployment/kubernetes/deploymentFiles/ditto/ditto-log-files.yaml

# Apply Ditto services
echo "Deploying Ditto services..."
kubectl apply -f deployment/kubernetes/deploymentFiles/ditto/

# Apply Swagger UI deployment
echo "Deploying Swagger UI..."
kubectl apply -f deployment/kubernetes/deploymentFiles/swagger/swagger.yaml

# Apply Nginx deployment
echo "Deploying Nginx..."
kubectl apply -f deployment/kubernetes/deploymentFiles/nginx/nginx.yaml

echo "Deployment completed successfully."
