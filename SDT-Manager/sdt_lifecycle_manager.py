# File: sdt_lifecycle_manager.py
import subprocess
import time
import logging
import os
import uuid
import re
from typing import Dict, Optional, List

YAML_PATH = os.environ.get("YAML_PATH", "/home/sdtm/SDTM/SDT-Manager/yaml_scripts/")
LOGGER = logging.getLogger(__name__)

class SDT_LifeCycleManager:
    """Handles the complete lifecycle of SDT deployments - creation and termination"""
    def __init__(self):
        """Initialize SDT Lifecycle Manager with deployment tracking"""
        self.pod_map = {}  # Store deployed pod names mapped to IDs
        LOGGER.info("SDT Lifecycle Manager initialized")
    
    def run_command(self, command: str) -> Optional[str]:
        """Execute a kubectl command and return the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            LOGGER.info(result.stdout)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            LOGGER.error(f"Command failed: {command}")
            LOGGER.error(f"Error output: {e.stderr}")
            return None

    # ----- Deployment Functions -----
    
    def deploy_pod(self):
        """Deploys the SDT pod and assigns a random identifier."""
        pod_id = uuid.uuid4().hex[:8]  # Generate a short hexadecimal identifier
        LOGGER.info(f"Deploying SDT pod with ID: {pod_id}")
        self.run_command(f"kubectl apply -f {YAML_PATH}sdt-pod-with-ditto-k3s-itr2.yaml")
        time.sleep(5)  # Give time for pod to be created
        pod_name = self.get_pod_name()
        if pod_name:
            self.pod_map[pod_name] = pod_id  # Store the pod name and ID mapping
            LOGGER.info(f"Mapped Pod Name: {pod_name} to ID: {pod_id}")
            LOGGER.info(f"Current Pod Map: {self.pod_map}")
            return pod_name, pod_id
        return None, None
    
    def get_pod_name(self):
        """Retrieves the name of the deployed SDT pod."""
        return self.run_command("kubectl get pods -l app=sdt -o jsonpath='{.items[0].metadata.name}'")
    
    def check_pod_running(self):
        """Checks if the SDT pod is running."""
        LOGGER.info("Checking if SDT pod is running...")
        for _ in range(30):  # Wait up to ~5 minutes total
            output = self.run_command("kubectl get pods -l app=sdt -o jsonpath='{.items[0].status.phase}'")
            if output and "Running" in output:
                LOGGER.info("SDT pod is running.")
                return True
            time.sleep(10)
        LOGGER.error("SDT pod did not start running within the expected time.")
        return False
    
    def deploy_service(self):
        """Deploys the SDT service."""
        LOGGER.info("Deploying SDT service...")
        self.run_command(f"kubectl apply -f {YAML_PATH}sdt-service.yaml")
    
    def deploy(self):
        """Complete deployment process for pod and service"""
        pod_name, pod_id = self.deploy_pod()
        if self.check_pod_running():
            self.deploy_service()
            return pod_name, pod_id
        else:
            LOGGER.error("Service deployment skipped because the pod is not running.")
            return None, None

    # ----- Deletion Functions -----
    
    def get_deployment_name_from_pod_name(self, pod_name: str) -> str:
        """
        Extract deployment name from pod name by finding the replicaset suffix.
        Example: from 'sdt-deployment-6b46d87fc-qpmgt' extracts 'sdt-deployment'
        
        Args:
            pod_name (str): Name of the pod
            
        Returns:
            str: Deployment name
        """
        # Pattern matches: hyphen followed by hash (8-10 chars) followed by hyphen and 5 chars
        pattern = r'-[a-zA-Z0-9]{8,10}-[a-zA-Z0-9]{5}$'
        match = re.search(pattern, pod_name)
        
        if match:
            # Return everything before the replicaset hash
            deployment_name = pod_name[:match.start()]
            LOGGER.debug(f"Extracted deployment name '{deployment_name}' from pod '{pod_name}'")
            return deployment_name
            
        # Fallback: if pattern not found, return the original name
        LOGGER.warning(f"Could not extract deployment name from pod '{pod_name}', using as is")
        return pod_name
    
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
    
    def delete_deployment_by_id(self, identifier: str) -> Dict[str, bool]:
        """
        Deletes a specific SDT deployment given its identifier.
        
        Returns:
            Dict[str, bool]: {identifier: True/False} indicating deletion success
        """
        # Find all pods with the matching identifier
        matching_pods = [(pname, pid) for pname, pid in self.pod_map.items() if pid == identifier]

        if not matching_pods:
            # No pods found with that identifier
            LOGGER.warning(f"No deployment found with identifier {identifier}")
            return {identifier: False}

        deletion_results = {}

        # Attempt to delete each matching pod's deployment
        for pod_name, _ in matching_pods:
            deployment_name = self.get_deployment_name_from_pod_name(pod_name)
            success = self.delete_deployment(deployment_name)

            deletion_results[identifier] = success
            if success:
                # Remove the pod_name from pod_map if the deletion succeeded
                del self.pod_map[pod_name]
                LOGGER.info(f"Removed {pod_name} from pod map after successful deletion.")

        return deletion_results
    
    # For CLI/Interactive usage
    def list_available_deployments(self):
        """
        List all available deployments and their identifiers.
        
        Returns:
            List[Dict]: List of deployment information dictionaries
        """
        deployments = []
        
        for pod_name, identifier in self.pod_map.items():
            deployment_name = self.get_deployment_name_from_pod_name(pod_name)
            deployments.append({
                "pod_name": pod_name,
                "identifier": identifier,
                "deployment_name": deployment_name
            })
        
        return deployments