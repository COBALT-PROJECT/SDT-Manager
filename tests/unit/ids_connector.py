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
    "consumer": [
        "be-dataapp-consumer-configmap.yaml",
        "ecc-consumer-configmap-v.2.yaml",
        "consumer-compiled-v-0.3.yaml"
    ],
    "provider": [
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
    
    def deploy_connector(self, connector_type: str = "consumer") -> Tuple[Optional[str], Optional[str]]:
        """
        Deploy the IDS connector with all required configurations.
        
        Args:
            connector_type (str): Type of connector to deploy ("consumer" or "provider")
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (deployment_name, connector_id) or (None, None) if failed
        """
        if connector_type not in ["consumer", "provider"]:
            LOGGER.error(f"Invalid connector type: {connector_type}. Must be 'consumer' or 'provider'")
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
        
        # Step 2: Wait for deployment to be ready and get deployment name
        time.sleep(10)  # Give more time for deployment to be created
        deployment_name = self.get_deployment_name(connector_type)
        
        if deployment_name:
            self.deployment_map[deployment_name] = connector_id
            LOGGER.info(f"Mapped Deployment: {deployment_name} to ID: {connector_id}")
            LOGGER.info(f"Current Deployment Map: {self.deployment_map}")
            return deployment_name, connector_id
        else:
            LOGGER.error("Could not retrieve deployment name")
            return None, None
    
    def get_deployment_name(self, connector_type: str = "consumer") -> Optional[str]:
        """Retrieve the name of the deployed IDS connector."""
        if connector_type == "consumer":
            command = "kubectl get deployments -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        elif connector_type == "provider":
            command = "kubectl get deployments -l io.kompose.service=tc-provider -o jsonpath='{.items[0].metadata.name}'"
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return None
        
        return self.run_command(command)
    
    def get_service_name(self, connector_type: str = "consumer") -> Optional[str]:
        """Retrieve the name of the deployed IDS connector service."""
        if connector_type == "consumer":
            command = "kubectl get services -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}'"
        elif connector_type == "provider":
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
    
    def deploy(self, connector_type: str = "consumer") -> Tuple[Optional[str], Optional[str]]:
        """
        Complete deployment process for IDS connector.
        
        Args:
            connector_type (str): Type of connector to deploy ("consumer" or "provider")
            
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
    
    def delete_configmaps(self, connector_type: str = "consumer") -> Dict[str, bool]:
        """Delete IDS connector related configmaps based on type."""
        results = {}
        
        # Delete shared configmaps
        shared_configmaps = ["ca-pemstore"]
        
        # Delete type-specific configmaps
        if connector_type == "consumer":
            type_configmaps = ["be-dataapp-consumer-configmap", "ecc-consumer-configmap"]
        elif connector_type == "provider":
            type_configmaps = ["be-dataapp-provider-configmap", "ecc-provider-configmap"]
        else:
            LOGGER.error(f"Unknown connector type: {connector_type}")
            return {"error": False}
        
        # Delete all configmaps
        all_configmaps = shared_configmaps + type_configmaps
        
        for configmap_name in all_configmaps:
            cmd = f"kubectl delete configmap {configmap_name}"
            result = self.run_command(cmd)
            results[configmap_name] = result is not None
            
        return results
    
    def delete_pvcs(self, connector_type: str = "consumer") -> Dict[str, bool]:
        """Delete IDS connector related persistent volume claims based on type."""
        results = {}
        
        if connector_type == "consumer":
            pvc_names = [
                "be-dataapp-consumer-claim0",
                "be-dataapp-consumer-claim1", 
                "be-dataapp-consumer-claim2",
                "ecc-consumer-claim0",
                "ecc-consumer-claim1"
            ]
        elif connector_type == "provider":
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
        if "consumer" in deployment_name.lower():
            return "consumer"
        elif "provider" in deployment_name.lower():
            return "provider"
        else:
            # Default to consumer if unable to determine
            LOGGER.warning(f"Unable to determine connector type from deployment name: {deployment_name}")
            return "consumer"
    
    def delete_connector_by_id(self, connector_id: str, cleanup_resources: bool = True) -> Dict[str, bool]:
        """
        Delete a specific IDS connector deployment given its identifier.
        
        Args:
            connector_id (str): The connector identifier
            cleanup_resources (bool): Whether to cleanup configmaps and PVCs
            
        Returns:
            Dict[str, bool]: Results of deletion operations
        """
        # Find deployments with the matching identifier
        matching_deployments = [
            (deployment_name, cid) 
            for deployment_name, cid in self.deployment_map.items() 
            if cid == connector_id
        ]

        if not matching_deployments:
            LOGGER.warning(f"No connector deployment found with identifier {connector_id}")
            return {connector_id: False}

        deletion_results = {}

        # Delete each matching deployment
        for deployment_name, _ in matching_deployments:
            connector_type = self.get_connector_type_from_deployment(deployment_name)
            
            # Delete deployment
            deployment_success = self.delete_deployment(deployment_name)
            deletion_results[f"deployment_{deployment_name}"] = deployment_success
            
            # Delete service
            service_name = self.get_service_name(connector_type)
            if service_name:
                service_success = self.delete_service(service_name)
                deletion_results[f"service_{service_name}"] = service_success
            
            # Cleanup resources if requested
            if cleanup_resources:
                # Delete configmaps
                configmap_results = self.delete_configmaps(connector_type)
                deletion_results.update({f"configmap_{k}": v for k, v in configmap_results.items()})
                
                # Delete PVCs
                pvc_results = self.delete_pvcs(connector_type)
                deletion_results.update({f"pvc_{k}": v for k, v in pvc_results.items()})
            
            # Remove from deployment map if deletion succeeded
            if deployment_success:
                del self.deployment_map[deployment_name]
                LOGGER.info(f"Removed {deployment_name} from deployment map after successful deletion")

        # Overall success if deployment deletion succeeded
        deletion_results[connector_id] = any(
            v for k, v in deletion_results.items() 
            if k.startswith("deployment_")
        )
        
        return deletion_results

    # ----- Status and Listing Functions -----
    
    def list_available_connectors(self) -> List[Dict]:
        """
        List all available IDS connector deployments and their identifiers.
        
        Returns:
            List[Dict]: List of connector deployment information dictionaries
        """
        connectors = []
        
        for deployment_name, connector_id in self.deployment_map.items():
            connector_type = self.get_connector_type_from_deployment(deployment_name)
            
            # Get deployment status
            status_cmd = f"kubectl get deployment {deployment_name} -o jsonpath='{{.status.readyReplicas}}/{{.spec.replicas}}'"
            status = self.run_command(status_cmd) or "Unknown"
            
            # Get service name
            service_name = self.get_service_name(connector_type)
            
            connectors.append({
                "deployment_name": deployment_name,
                "connector_id": connector_id,
                "service_name": service_name,
                "status": status,
                "type": connector_type
            })
        
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
        
        # Pod status
        label_selector = f"io.kompose.service=tc-{connector_type}"
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