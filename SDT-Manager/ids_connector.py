# File: ids_connector.py
import subprocess
import time
import logging
import uuid
import re
from typing import Dict, Optional, List, Tuple

# Base path for IDS connector YAML files
IDS_YAML_BASE_PATH = "/home/ubuntu/true-connector/kubernetes/"

# IDS Connector configuration files
IDS_CONFIG_FILES = {
    "shared": [
        "ca-pemstore.yaml"
    ],
    "ids_sdt": [
        "be-dataapp-consumer-configmap.yaml",
        "ecc-consumer-configmap-v.2.yaml",
        "consumer-compiled-v-0.3.yaml",
        "ids_connector_sdt_k8s_deployment.yml",
        "pods_sync_k3s.yml"
        # Removed pods_sync_monitor.yml as it requires Prometheus CRDs
    ],
    "ids_toe": [
        "be-dataapp-provider-configmap.yaml", 
        "ecc-provider-configmap-v.2.yaml",
        "provider-compiled-v-0.3.yaml"
    ]
}

LOGGER = logging.getLogger(__name__)

class IDS_Connector:
    """Handles the complete lifecycle of IDS Connector deployments - creation and termination"""
    
    def __init__(self):
        """Initialize IDS Connector Manager with deployment tracking"""
        self.deployment_map = {}  # Store deployed connector names mapped to IDs
        self.yaml_base_path = IDS_YAML_BASE_PATH
        self.config_files = IDS_CONFIG_FILES.copy()
        LOGGER.info("IDS Connector Manager initialized")
    
    def run_command(self, command: str) -> Optional[str]:
        """Execute a kubectl command and return the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            LOGGER.info(f"Command executed successfully: {command}")
            LOGGER.debug(f"Command output: {result.stdout}")
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            LOGGER.error(f"Command failed: {command}")
            LOGGER.error(f"Error output: {e.stderr}")
            LOGGER.error(f"Return code: {e.returncode}")
            return None

    # ----- Configuration Management -----
    
    def apply_config_file(self, config_file: str) -> bool:
        """Apply a single configuration file from local path"""
        file_path = f"{self.yaml_base_path}{config_file}"
        LOGGER.info(f"Applying {config_file} from {file_path}")
        command = f"kubectl apply -f {file_path}"
        result = self.run_command(command)
        
        if result is not None:
            LOGGER.info(f"Successfully applied {config_file}")
            return True
        else:
            LOGGER.error(f"Failed to apply {config_file}")
            return False
    
    def apply_configs_for_type(self, connector_type: str) -> Dict[str, bool]:
        """Apply all required configuration files for a specific connector type"""
        results = {}
        
        # Apply shared configurations first
        LOGGER.info("Applying shared configurations...")
        for config_file in self.config_files["shared"]:
            success = self.apply_config_file(config_file)
            results[f"shared_{config_file}"] = success
            
            if not success:
                LOGGER.error(f"Failed to apply shared config {config_file}, stopping deployment")
                return results
            
            # Small delay between applying configs
            time.sleep(2)
        
        # Apply connector-specific configurations
        LOGGER.info(f"Applying {connector_type} specific configurations...")
        if connector_type not in self.config_files:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            results[f"error"] = False
            return results
        
        for config_file in self.config_files[connector_type]:
            success = self.apply_config_file(config_file)
            results[f"{connector_type}_{config_file}"] = success
            
            if not success:
                LOGGER.error(f"Failed to apply {connector_type} config {config_file}, stopping deployment")
                return results
            
            # Small delay between applying configs
            time.sleep(2)
        
        return results

    # ----- Deployment Functions -----
    
    def deploy_connector(self, connector_type: str = "ids_sdt") -> Tuple[Optional[str], Optional[str]]:
        """
        Deploy the IDS connector with all required configurations.
        
        Args:
            connector_type (str): Type of connector to deploy ("ids_sdt" or "ids_toe")
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (deployment_name, connector_id) or (None, None) if failed
        """
        if connector_type not in ["ids_sdt", "ids_toe"]:
            LOGGER.error(f"Invalid connector type: {connector_type}. Must be 'ids_sdt' or 'ids_toe'")
            return None, None
        
        connector_id = uuid.uuid4().hex[:8]  # Generate a short hexadecimal identifier
        LOGGER.info(f"Starting IDS {connector_type} connector deployment with ID: {connector_id}")
        
        # Step 1: Apply all configuration files
        LOGGER.info("Applying configuration files...")
        config_results = self.apply_configs_for_type(connector_type)
        
        # Check if all configs were applied successfully
        failed_configs = [name for name, success in config_results.items() if not success]
        if failed_configs:
            LOGGER.error(f"Failed to apply configurations: {failed_configs}")
            return None, None
        
        LOGGER.info("All configuration files applied successfully")
        
        # Step 2: Wait for deployments to be ready and get deployment names
        time.sleep(10)  # Give more time for deployments to be created
        
        if connector_type == "ids_sdt":
            # For ids_sdt, we have THREE deployments to track
            # Wait a bit longer for all deployments to be created
            time.sleep(5)
            
            tc_consumer_name = self.get_tc_consumer_deployment_name()
            ids_sdt_name = self.get_ids_sdt_deployment_name()
            ids_sync_name = self.get_ids_sync_deployment_name()
            
            deployment_count = 0
            primary_deployment = None
            
            if tc_consumer_name:
                self.deployment_map[tc_consumer_name] = connector_id
                LOGGER.info(f"Mapped tc-consumer Deployment: {tc_consumer_name} to ID: {connector_id}")
                deployment_count += 1
                primary_deployment = tc_consumer_name
            
            if ids_sdt_name:
                self.deployment_map[ids_sdt_name] = connector_id
                LOGGER.info(f"Mapped ids-connector-sdt Deployment: {ids_sdt_name} to ID: {connector_id}")
                deployment_count += 1
                if not primary_deployment:
                    primary_deployment = ids_sdt_name
            
            if ids_sync_name:
                self.deployment_map[ids_sync_name] = connector_id
                LOGGER.info(f"Mapped ids-sync-service Deployment: {ids_sync_name} to ID: {connector_id}")
                deployment_count += 1
                if not primary_deployment:
                    primary_deployment = ids_sync_name
            
            if primary_deployment:
                LOGGER.info(f"Total deployments mapped: {deployment_count}")
                LOGGER.info(f"Current Deployment Map: {self.deployment_map}")
                return primary_deployment, connector_id
            else:
                LOGGER.error("Could not retrieve any deployment names")
                return None, None
        else:
            # For ids_toe, single deployment
            deployment_name = self.get_deployment_name(connector_type)
            
            if deployment_name:
                self.deployment_map[deployment_name] = connector_id
                LOGGER.info(f"Mapped Deployment: {deployment_name} to ID: {connector_id}")
                LOGGER.info(f"Current Deployment Map: {self.deployment_map}")
                return deployment_name, connector_id
            else:
                LOGGER.error("Could not retrieve deployment name")
                return None, None
    
    def get_tc_consumer_deployment_name(self) -> Optional[str]:
        """Retrieve the name of the tc-consumer deployment."""
        command = "kubectl get deployments -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        return self.run_command(command)
    
    def get_ids_sdt_deployment_name(self) -> Optional[str]:
        """Retrieve the name of the ids-connector-sdt deployment."""
        command = "kubectl get deployment ids-connector-sdt-deployment -o jsonpath='{.metadata.name}' --ignore-not-found=true"
        return self.run_command(command)
    
    def get_ids_sync_deployment_name(self) -> Optional[str]:
        """Retrieve the name of the ids-sync-service deployment."""
        command = "kubectl get deployment ids-sync-service -o jsonpath='{.metadata.name}' --ignore-not-found=true"
        return self.run_command(command)
    
    def get_deployment_name(self, connector_type: str = "ids_sdt") -> Optional[str]:
        """Retrieve the name of the deployed IDS connector."""
        if connector_type == "ids_sdt":
            # First check for the new ids-connector-sdt deployment
            command = "kubectl get deployments -l app=ids-connector-sdt -o jsonpath='{.items[0].metadata.name}'"
            result = self.run_command(command)
            if result:
                return result
            # Fall back to original consumer deployment if new one doesn't exist
            command = "kubectl get deployments -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        elif connector_type == "ids_toe":
            command = "kubectl get deployments -l io.kompose.service=tc-provider -o jsonpath='{.items[0].metadata.name}'"
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return None
        
        return self.run_command(command)
    
    def get_service_name(self, connector_type: str = "ids_sdt") -> Optional[str]:
        """Retrieve the name of the deployed IDS connector service."""
        if connector_type == "ids_sdt":
            # First check for the new ids-connector-sdt service
            # Using --ignore-not-found to avoid error if service doesn't exist
            command = "kubectl get services ids-connector-sdt-service -o jsonpath='{.metadata.name}' --ignore-not-found=true"
            result = self.run_command(command)
            if result:
                return result
            # Fall back to original consumer service if new one doesn't exist
            command = "kubectl get services -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        elif connector_type == "ids_toe":
            command = "kubectl get services -l io.kompose.service=tc-provider -o jsonpath='{.items[0].metadata.name}'"
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return None
        
        return self.run_command(command)
    
    def check_deployment_ready(self, deployment_name: str, timeout: int = 300) -> bool:
        """
        Check if the IDS connector deployment is ready.
        
        Args:
            deployment_name (str): Name of the deployment to check
            timeout (int): Maximum time to wait in seconds (default: 5 minutes)
            
        Returns:
            bool: True if deployment is ready, False otherwise
        """
        LOGGER.info(f"Checking if deployment {deployment_name} is ready...")
        
        for attempt in range(timeout // 10):  # Check every 10 seconds
            command = f"kubectl get deployment {deployment_name} -o jsonpath='{{.status.readyReplicas}}'"
            ready_replicas = self.run_command(command)
            
            command = f"kubectl get deployment {deployment_name} -o jsonpath='{{.spec.replicas}}'"
            desired_replicas = self.run_command(command)
            
            if ready_replicas and desired_replicas and ready_replicas == desired_replicas:
                LOGGER.info(f"Deployment {deployment_name} is ready ({ready_replicas}/{desired_replicas} replicas)")
                return True
            
            LOGGER.debug(f"Deployment {deployment_name} not ready yet ({ready_replicas}/{desired_replicas} replicas). Waiting...")
            time.sleep(10)
        
        LOGGER.error(f"Deployment {deployment_name} did not become ready within {timeout} seconds")
        return False
    
    def deploy(self, connector_type: str = "ids_sdt") -> Tuple[Optional[str], Optional[str]]:
        """
        Complete deployment process for IDS connector.
        
        Args:
            connector_type (str): Type of connector to deploy ("ids_sdt" or "ids_toe")
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (deployment_name, connector_id) if successful, (None, None) if failed
        """
        deployment_name, connector_id = self.deploy_connector(connector_type)
        
        if deployment_name and self.check_deployment_ready(deployment_name):
            LOGGER.info(f"IDS {connector_type} connector deployment completed successfully")
            return deployment_name, connector_id
        else:
            LOGGER.error(f"IDS {connector_type} connector deployment failed")
            return None, None

    # ----- Deletion Functions -----
    
    def delete_deployment(self, deployment_name: str) -> bool:
        """Delete a deployment using kubectl delete command."""
        cmd = f"kubectl delete deployment {deployment_name}"
        result = self.run_command(cmd)
        
        if result is not None:
            LOGGER.info(f"Successfully deleted deployment: {deployment_name}")
            return True
        else:
            LOGGER.error(f"Failed to delete deployment: {deployment_name}")
            return False
    
    def delete_service(self, service_name: str) -> bool:
        """Delete a service using kubectl delete command."""
        cmd = f"kubectl delete service {service_name}"
        result = self.run_command(cmd)
        
        if result is not None:
            LOGGER.info(f"Successfully deleted service: {service_name}")
            return True
        else:
            LOGGER.error(f"Failed to delete service: {service_name}")
            return False
    
    def delete_configmaps(self, connector_type: str = "ids_sdt") -> Dict[str, bool]:
        """Delete IDS connector related configmaps based on type."""
        results = {}
        
        # Delete shared configmaps
        shared_configmaps = ["ca-pemstore"]
        
        # Delete type-specific configmaps
        if connector_type == "ids_sdt":
            type_configmaps = [
                "be-dataapp-consumer-configmap", 
                "ecc-consumer-configmap",
                "ids-connector-sdt-configmap",  # From ids_connector_sdt_k8s_deployment.yml
                "ids-sync-config"  # From pods_sync_k3s.yml
                # Removed grafana-dashboard-ids-sync as we're not deploying monitoring
            ]
        elif connector_type == "ids_toe":
            type_configmaps = ["be-dataapp-provider-configmap", "ecc-provider-configmap"]
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        # Delete all configmaps
        all_configmaps = shared_configmaps + type_configmaps
        
        for configmap_name in all_configmaps:
            cmd = f"kubectl delete configmap {configmap_name} --ignore-not-found=true"
            result = self.run_command(cmd)
            results[configmap_name] = result is not None
            
        return results
    
    def delete_secrets(self, connector_type: str = "ids_sdt") -> Dict[str, bool]:
        """Delete IDS connector related secrets based on type."""
        results = {}
        
        if connector_type == "ids_sdt":
            secret_names = [
                "ids-connector-sdt-secret",  # From ids_connector_sdt_k8s_deployment.yml
                "ids-sync-credentials"  # From pods_sync_k3s.yml
            ]
        elif connector_type == "ids_toe":
            secret_names = []  # No secrets for ids_toe currently
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        for secret_name in secret_names:
            cmd = f"kubectl delete secret {secret_name} --ignore-not-found=true"
            result = self.run_command(cmd)
            results[secret_name] = result is not None
            
        return results
    
    def delete_pvcs(self, connector_type: str = "ids_sdt") -> Dict[str, bool]:
        """Delete IDS connector related persistent volume claims based on type."""
        results = {}
        
        if connector_type == "ids_sdt":
            pvc_names = [
                "be-dataapp-consumer-claim0",
                "be-dataapp-consumer-claim1", 
                "be-dataapp-consumer-claim2",
                "ecc-consumer-claim0",
                "ecc-consumer-claim1"
            ]
        elif connector_type == "ids_toe":
            pvc_names = [
                "be-dataapp-provider-claim0",
                "be-dataapp-provider-claim1", 
                "be-dataapp-provider-claim2",
                "ecc-provider-claim0",
                "ecc-provider-claim1"
            ]
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        for pvc_name in pvc_names:
            cmd = f"kubectl delete pvc {pvc_name} --ignore-not-found=true"
            result = self.run_command(cmd)
            results[pvc_name] = result is not None
            
        return results
        
        for configmap_name in all_configmaps:
            cmd = f"kubectl delete configmap {configmap_name}"
            result = self.run_command(cmd)
            results[configmap_name] = result is not None
            
        return results
    
    def delete_secrets(self, connector_type: str = "ids_sdt") -> Dict[str, bool]:
        """Delete IDS connector related secrets based on type."""
        results = {}
        
        if connector_type == "ids_sdt":
            secret_names = ["ids-connector-sdt-secret"]
        elif connector_type == "ids_toe":
            secret_names = []  # No secrets for ids_toe currently
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        for secret_name in secret_names:
            cmd = f"kubectl delete secret {secret_name}"
            result = self.run_command(cmd)
            results[secret_name] = result is not None
            
        return results
        """Delete IDS connector related persistent volume claims based on type."""
        results = {}
        
        if connector_type == "ids_sdt":
            pvc_names = [
                "be-dataapp-consumer-claim0",
                "be-dataapp-consumer-claim1", 
                "be-dataapp-consumer-claim2",
                "ecc-consumer-claim0",
                "ecc-consumer-claim1"
            ]
        elif connector_type == "ids_toe":
            pvc_names = [
                "be-dataapp-provider-claim0",
                "be-dataapp-provider-claim1", 
                "be-dataapp-provider-claim2",
                "ecc-provider-claim0",
                "ecc-provider-claim1"
            ]
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        for pvc_name in pvc_names:
            cmd = f"kubectl delete pvc {pvc_name}"
            result = self.run_command(cmd)
            results[pvc_name] = result is not None
            
        return results
    
    def get_connector_type_from_deployment(self, deployment_name: str) -> str:
        """Determine connector type from deployment name."""
        if "ids-connector-sdt" in deployment_name.lower() or "consumer" in deployment_name.lower():
            return "ids_sdt"
        elif "provider" in deployment_name.lower():
            return "ids_toe"
        else:
            # Default to ids_sdt if unable to determine
            LOGGER.warning(f"Unable to determine connector type from deployment name: {deployment_name}")
            return "ids_sdt"
    
    def delete_connector_by_id(self, connector_id: str, cleanup_resources: bool = True) -> Dict[str, bool]:
        """
        Delete a specific IDS connector deployment given its identifier.
        For ids_sdt, this deletes ALL three deployments: tc-consumer, ids-connector-sdt, and ids-sync-service.
        
        Args:
            connector_id (str): The connector identifier
            cleanup_resources (bool): Whether to cleanup configmaps and PVCs
            
        Returns:
            Dict[str, bool]: Results of deletion operations
        """
        # Find ALL deployments with the matching identifier
        matching_deployments = [
            (deployment_name, cid) 
            for deployment_name, cid in self.deployment_map.items() 
            if cid == connector_id
        ]

        if not matching_deployments:
            LOGGER.warning(f"No connector deployment found with identifier {connector_id}")
            return {connector_id: False}

        deletion_results = {}
        connector_type = None
        
        # Delete each matching deployment (there can be multiple for ids_sdt)
        for deployment_name, _ in matching_deployments:
            # Determine connector type from first deployment if not set
            if connector_type is None:
                connector_type = self.get_connector_type_from_deployment(deployment_name)
                LOGGER.info(f"Detected connector type: {connector_type} for deployment: {deployment_name}")
            
            # Delete the deployment
            deployment_success = self.delete_deployment(deployment_name)
            deletion_results[f"deployment_{deployment_name}"] = deployment_success
            
            if deployment_success:
                # Remove from deployment map immediately after successful deletion
                del self.deployment_map[deployment_name]
                LOGGER.info(f"Removed {deployment_name} from deployment map after successful deletion")
        
        # Now handle services - for ids_sdt we may have multiple services
        if connector_type == "ids_sdt":
            # Delete tc-consumer service
            tc_consumer_service = self.get_tc_consumer_service_name()
            if tc_consumer_service:
                service_success = self.delete_service(tc_consumer_service)
                deletion_results[f"service_{tc_consumer_service}"] = service_success
                LOGGER.info(f"Deleted tc-consumer service: {tc_consumer_service}")
            
            # Delete ids-connector-sdt service
            ids_sdt_service = "ids-connector-sdt-service"
            check_cmd = f"kubectl get service {ids_sdt_service} --ignore-not-found=true -o jsonpath='{{.metadata.name}}'"
            if self.run_command(check_cmd):
                service_success = self.delete_service(ids_sdt_service)
                deletion_results[f"service_{ids_sdt_service}"] = service_success
                LOGGER.info(f"Deleted ids-connector-sdt service: {ids_sdt_service}")
            
            # Delete ids-sync-service
            ids_sync_service = "ids-sync-service"
            check_cmd = f"kubectl get service {ids_sync_service} --ignore-not-found=true -o jsonpath='{{.metadata.name}}'"
            if self.run_command(check_cmd):
                service_success = self.delete_service(ids_sync_service)
                deletion_results[f"service_{ids_sync_service}"] = service_success
                LOGGER.info(f"Deleted ids-sync service: {ids_sync_service}")
        elif connector_type == "ids_toe":
            # For ids_toe, get and delete the provider service
            provider_service = self.get_service_name(connector_type)
            if provider_service:
                service_success = self.delete_service(provider_service)
                deletion_results[f"service_{provider_service}"] = service_success
                LOGGER.info(f"Deleted provider service: {provider_service}")
        
        # Cleanup resources if requested
        if cleanup_resources and connector_type:
            # Delete configmaps
            configmap_results = self.delete_configmaps(connector_type)
            deletion_results.update({f"configmap_{k}": v for k, v in configmap_results.items()})
            
            # Delete secrets
            secret_results = self.delete_secrets(connector_type)
            deletion_results.update({f"secret_{k}": v for k, v in secret_results.items()})
            
            # Delete PVCs
            pvc_results = self.delete_pvcs(connector_type)
            deletion_results.update({f"pvc_{k}": v for k, v in pvc_results.items()})
        
        # Overall success if at least one deployment deletion succeeded
        deletion_results[connector_id] = any(
            v for k, v in deletion_results.items() 
            if k.startswith("deployment_") and v
        )
        
        LOGGER.info(f"Deletion results for connector {connector_id}: {deletion_results}")
        return deletion_results
    
    def get_tc_consumer_service_name(self) -> Optional[str]:
        """Retrieve the name of the tc-consumer service."""
        command = "kubectl get services -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        return self.run_command(command)

    # ----- Status and Listing Functions -----
    
    def list_available_connectors(self) -> List[Dict]:
        """
        List all available IDS connector deployments and their identifiers.
        Groups deployments by connector_id for ids_sdt which has multiple deployments.
        
        Returns:
            List[Dict]: List of connector deployment information dictionaries
        """
        # Group deployments by connector_id
        connector_groups = {}
        
        for deployment_name, connector_id in self.deployment_map.items():
            if connector_id not in connector_groups:
                connector_groups[connector_id] = []
            connector_groups[connector_id].append(deployment_name)
        
        connectors = []
        
        for connector_id, deployment_names in connector_groups.items():
            # Determine connector type from first deployment
            connector_type = self.get_connector_type_from_deployment(deployment_names[0])
            
            # Build deployment info
            deployment_info = {
                "connector_id": connector_id,
                "type": connector_type,
                "deployments": []
            }
            
            # Add info for each deployment
            for deployment_name in deployment_names:
                # Get deployment status
                status_cmd = f"kubectl get deployment {deployment_name} -o jsonpath='{{.status.readyReplicas}}/{{.spec.replicas}}' --ignore-not-found=true"
                status = self.run_command(status_cmd) or "Unknown"
                
                deployment_info["deployments"].append({
                    "name": deployment_name,
                    "status": status
                })
            
            # Get services for this connector type
            services = []
            if connector_type == "ids_sdt":
                # Check for tc-consumer service
                tc_service = self.get_tc_consumer_service_name()
                if tc_service:
                    services.append(tc_service)
                
                # Check for ids-connector-sdt service  
                check_cmd = "kubectl get service ids-connector-sdt-service --ignore-not-found=true -o jsonpath='{.metadata.name}'"
                ids_service = self.run_command(check_cmd)
                if ids_service:
                    services.append(ids_service)
            else:
                # For ids_toe
                service = self.get_service_name(connector_type)
                if service:
                    services.append(service)
            
            deployment_info["services"] = services
            
            # Overall status - ready if all deployments are ready
            all_ready = all(
                "1/1" in dep.get("status", "") 
                for dep in deployment_info["deployments"]
            )
            deployment_info["overall_status"] = "Ready" if all_ready else "Not Ready"
            
            connectors.append(deployment_info)
        
        return connectors
    
    def get_connector_status(self, connector_id: str) -> Optional[Dict]:
        """
        Get detailed status of a specific connector.
        
        Args:
            connector_id (str): The connector identifier
            
        Returns:
            Optional[Dict]: Connector status information or None if not found
        """
        # Find deployment with matching ID
        deployment_name = None
        for dep_name, cid in self.deployment_map.items():
            if cid == connector_id:
                deployment_name = dep_name
                break
        
        if not deployment_name:
            return None
        
        connector_type = self.get_connector_type_from_deployment(deployment_name)
        
        # Get detailed status
        status_info = {}
        
        # Deployment status
        ready_cmd = f"kubectl get deployment {deployment_name} -o jsonpath='{{.status.readyReplicas}}'"
        desired_cmd = f"kubectl get deployment {deployment_name} -o jsonpath='{{.spec.replicas}}'"
        
        ready_replicas = self.run_command(ready_cmd) or "0"
        desired_replicas = self.run_command(desired_cmd) or "0"
        
        # Pod status - still using old labels as they haven't changed in k8s
        if connector_type == "ids_sdt":
            label_selector = "io.kompose.service=tc-consumer"
        else:
            label_selector = "io.kompose.service=tc-provider"
        pods_cmd = f"kubectl get pods -l {label_selector} -o jsonpath='{{.items[*].status.phase}}'"
        pod_statuses = self.run_command(pods_cmd) or ""
        
        status_info = {
            "connector_id": connector_id,
            "deployment_name": deployment_name,
            "connector_type": connector_type,
            "ready_replicas": ready_replicas,
            "desired_replicas": desired_replicas,
            "is_ready": ready_replicas == desired_replicas and ready_replicas != "0",
            "pod_statuses": pod_statuses.split() if pod_statuses else [],
            "service_name": self.get_service_name(connector_type)
        }
        
        return status_info