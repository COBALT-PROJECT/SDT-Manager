# File: watchtower_manager.py
import subprocess
import time
import logging
import uuid
import re
import os
from typing import Dict, Optional, List, Tuple

# Get YAML path from environment variable or use default
YAML_PATH = os.getenv('YAML_PATH', "/home/sdtm/SDTM/SDT-Manager/yaml_scripts/")
LOGGER = logging.getLogger(__name__)


class WatchTower_LifeCycleManager:
    """Handles the complete lifecycle of Watchtower deployments - creation, monitoring, and termination"""
    
    def __init__(self):
        """Initialize Watchtower Lifecycle Manager with deployment tracking"""
        self.watchtower_map = {}  # Store deployed watchtower names mapped to IDs
        self.yaml_path = YAML_PATH
        LOGGER.info("Watchtower Lifecycle Manager initialized")
    
    def run_command(self, command: str) -> Optional[str]:
        """
        Execute a kubectl command and return the output.
        
        Args:
            command (str): The kubectl command to execute
            
        Returns:
            Optional[str]: Command output if successful, None if failed
        """
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                check=True, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            LOGGER.info(result.stdout)
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            LOGGER.error(f"Command timed out: {command}")
            return None
        except subprocess.CalledProcessError as e:
            LOGGER.error(f"Command failed: {command}")
            LOGGER.error(f"Error output: {e.stderr}")
            return None
    
    # ----- Deployment Functions -----
    
    def deploy_watchtower_pod(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Deploys the Watchtower pod and assigns a random identifier.
        
        Returns:
            Tuple[Optional[str], Optional[str]]: (pod_name, watchtower_id) or (None, None) if failed
        """
        watchtower_id = uuid.uuid4().hex[:8]  # Generate a short hexadecimal identifier
        LOGGER.info(f"Deploying Watchtower pod with ID: {watchtower_id}")
        
        # Apply the deployment YAML
        deployment_path = f"{self.yaml_path}watchtower-deployment.yaml"
        LOGGER.info(f"Applying deployment from: {deployment_path}")
        
        result = self.run_command(f"kubectl apply -f {deployment_path}")
        if not result:
            LOGGER.error("Failed to apply Watchtower deployment YAML")
            return None, None
        
        time.sleep(5)  # Give time for pod to be created
        
        # Get the pod name
        pod_name = self.get_watchtower_pod_name()
        if pod_name:
            self.watchtower_map[pod_name] = watchtower_id  # Store the pod name and ID mapping
            LOGGER.info(f"Mapped Watchtower Pod Name: {pod_name} to ID: {watchtower_id}")
            LOGGER.info(f"Current Watchtower Map: {self.watchtower_map}")
            return pod_name, watchtower_id
        else:
            LOGGER.error("Failed to retrieve Watchtower pod name")
            return None, None
    
    def get_watchtower_pod_name(self) -> Optional[str]:
        """
        Retrieves the name of the deployed Watchtower pod.
        
        Returns:
            Optional[str]: Pod name if found, None otherwise
        """
        pod_name = self.run_command("kubectl get pods -l app=watchtower -o jsonpath='{.items[0].metadata.name}'")
        if pod_name:
            LOGGER.info(f"Retrieved Watchtower pod name: {pod_name}")
        else:
            LOGGER.warning("No Watchtower pod found")
        return pod_name
    
    def check_watchtower_running(self) -> bool:
        """
        Checks if the Watchtower pod is running.
        Waits up to 5 minutes for the pod to start.
        
        Returns:
            bool: True if pod is running, False otherwise
        """
        LOGGER.info("Checking if Watchtower pod is running...")
        max_attempts = 30
        check_interval = 10  # seconds
        
        for attempt in range(max_attempts):
            output = self.run_command("kubectl get pods -l app=watchtower -o jsonpath='{.items[0].status.phase}'")
            if output and "Running" in output:
                LOGGER.info("Watchtower pod is running.")
                return True
            
            LOGGER.debug(f"Attempt {attempt + 1}/{max_attempts}: Watchtower pod status: {output}")
            time.sleep(check_interval)
        
        LOGGER.error("Watchtower pod did not start running within the expected time.")
        return False
    
    def deploy_watchtower_service(self) -> bool:
        """
        Deploys the Watchtower service.
        
        Returns:
            bool: True if service deployed successfully, False otherwise
        """
        LOGGER.info("Deploying Watchtower service...")
        service_path = f"{self.yaml_path}watchtower-service.yaml"
        LOGGER.info(f"Applying service from: {service_path}")
        
        result = self.run_command(f"kubectl apply -f {service_path}")
        if result:
            LOGGER.info("Watchtower service deployed successfully")
            return True
        else:
            LOGGER.error("Failed to deploy Watchtower service")
            return False
    
    def deploy_watchtower(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Complete deployment process for Watchtower pod and service.
        
        This is the main deployment method that orchestrates the entire deployment process:
        1. Deploy the pod
        2. Wait for pod to be running
        3. Deploy the service
        
        Returns:
            Tuple[Optional[str], Optional[str]]: (pod_name, watchtower_id) or (None, None) if failed
        """
        LOGGER.info("Starting Watchtower deployment process...")
        
        # Deploy the pod
        pod_name, watchtower_id = self.deploy_watchtower_pod()
        
        if not pod_name or not watchtower_id:
            LOGGER.error("Watchtower pod deployment failed")
            return None, None
        
        # Check if pod is running
        if self.check_watchtower_running():
            # Deploy the service
            if self.deploy_watchtower_service():
                LOGGER.info(f"Watchtower deployment complete: {pod_name} (ID: {watchtower_id})")
                return pod_name, watchtower_id
            else:
                LOGGER.warning("Watchtower pod is running but service deployment failed")
                return pod_name, watchtower_id
        else:
            LOGGER.error("Watchtower service deployment skipped because the pod is not running.")
            return None, None
    
    # ----- Information and Status Functions -----
    
    def get_deployment_name_from_pod_name(self, pod_name: str) -> str:
        """
        Extract deployment name from pod name by finding the replicaset suffix.
        Example: from 'watchtower-deployment-6b46d87fc-qpmgt' extracts 'watchtower-deployment'
        
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
    
    def get_watchtower_info(self, watchtower_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific Watchtower deployment.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            
        Returns:
            Optional[Dict]: Watchtower information dictionary or None if not found
        """
        # Find pod with matching identifier
        matching_pod = None
        pod_name = None
        
        for pname, wid in self.watchtower_map.items():
            if wid == watchtower_id:
                matching_pod = wid
                pod_name = pname
                break
        
        if not matching_pod:
            LOGGER.warning(f"No Watchtower found with identifier {watchtower_id}")
            return None
        
        # Get deployment name
        deployment_name = self.get_deployment_name_from_pod_name(pod_name)
        
        # Get pod status
        status_cmd = f"kubectl get pod {pod_name} -o jsonpath='{{.status.phase}}'"
        pod_status = self.run_command(status_cmd) or "Unknown"
        
        # Get node info
        node_cmd = f"kubectl get pod {pod_name} -o jsonpath='{{.spec.nodeName}}'"
        node_name = self.run_command(node_cmd) or "Unknown"
        
        # Get pod IP
        pod_ip_cmd = f"kubectl get pod {pod_name} -o jsonpath='{{.status.podIP}}'"
        pod_ip = self.run_command(pod_ip_cmd) or "Unknown"
        
        # Get service info
        service_cmd = "kubectl get service watchtower-service -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null"
        node_port = self.run_command(service_cmd) or "Unknown"
        
        # Get service cluster IP
        service_ip_cmd = "kubectl get service watchtower-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null"
        service_ip = self.run_command(service_ip_cmd) or "Unknown"
        
        info = {
            "watchtower_id": watchtower_id,
            "pod_name": pod_name,
            "deployment_name": deployment_name,
            "status": pod_status,
            "node": node_name,
            "pod_ip": pod_ip,
            "service_name": "watchtower-service",
            "service_ip": service_ip,
            "node_port": node_port
        }
        
        LOGGER.info(f"Retrieved information for Watchtower {watchtower_id}")
        return info
    
    def list_watchtowers(self) -> List[Dict]:
        """
        List all deployed Watchtower instances with their information.
        
        Returns:
            List[Dict]: List of Watchtower information dictionaries
        """
        LOGGER.info(f"Listing all Watchtower instances (total: {len(self.watchtower_map)})")
        watchtowers = []
        
        for pod_name, watchtower_id in self.watchtower_map.items():
            info = self.get_watchtower_info(watchtower_id)
            if info:
                watchtowers.append(info)
        
        return watchtowers
    
    def get_watchtower_status(self, watchtower_id: str) -> Optional[str]:
        """
        Get the current status of a Watchtower pod.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            
        Returns:
            Optional[str]: Pod status (Running, Pending, Failed, etc.) or None if not found
        """
        info = self.get_watchtower_info(watchtower_id)
        if info:
            return info.get("status")
        return None
    
    def check_watchtower_exists(self, watchtower_id: str) -> bool:
        """
        Check if a Watchtower with the given ID exists.
        
        Args:
            watchtower_id (str): The Watchtower identifier to check
            
        Returns:
            bool: True if Watchtower exists, False otherwise
        """
        return any(wid == watchtower_id for wid in self.watchtower_map.values())
    
    def get_watchtower_logs(self, watchtower_id: str, lines: int = 100) -> Optional[str]:
        """
        Get logs for a specific Watchtower instance.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            lines (int): Number of log lines to retrieve (default: 100)
            
        Returns:
            Optional[str]: Watchtower logs or None if not found
        """
        # Find pod with matching ID
        pod_name = None
        for pname, wid in self.watchtower_map.items():
            if wid == watchtower_id:
                pod_name = pname
                break
        
        if not pod_name:
            LOGGER.warning(f"No pod found for Watchtower {watchtower_id}")
            return None
        
        # Get logs using kubectl
        cmd = f"kubectl logs {pod_name} --tail={lines}"
        logs = self.run_command(cmd)
        
        if logs:
            LOGGER.info(f"Retrieved {lines} lines of logs for Watchtower {watchtower_id}")
            return logs
        else:
            LOGGER.warning(f"No logs available for Watchtower {watchtower_id}")
            return None
    
    # ----- Deletion Functions -----
    
    def delete_deployment(self, deployment_name: str) -> bool:
        """
        Delete a Kubernetes deployment.
        
        Args:
            deployment_name (str): Name of the deployment to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        LOGGER.info(f"Deleting deployment: {deployment_name}")
        cmd = f"kubectl delete deployment {deployment_name}"
        result = self.run_command(cmd)
        
        if result is not None:
            LOGGER.info(f"Successfully deleted deployment: {deployment_name}")
            return True
        else:
            LOGGER.error(f"Failed to delete deployment: {deployment_name}")
            return False
    
    def delete_watchtower_service(self) -> bool:
        """
        Delete the Watchtower service.
        
        Returns:
            bool: True if service deleted successfully, False otherwise
        """
        LOGGER.info("Deleting Watchtower service")
        cmd = "kubectl delete service watchtower-service"
        result = self.run_command(cmd)
        
        if result is not None:
            LOGGER.info("Successfully deleted Watchtower service")
            return True
        else:
            LOGGER.error("Failed to delete Watchtower service")
            return False
    
    def delete_watchtower_by_id(self, watchtower_id: str, cleanup_service: bool = True) -> Dict[str, bool]:
        """
        Delete a specific Watchtower deployment given its identifier.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            cleanup_service (bool): Whether to also delete the service (default: True)
            
        Returns:
            Dict[str, bool]: Deletion results with keys for each component deleted
        """
        LOGGER.info(f"Deleting Watchtower with ID: {watchtower_id} (cleanup_service={cleanup_service})")
        
        # Find all pods with the matching identifier
        matching_pods = [(pname, wid) for pname, wid in self.watchtower_map.items() if wid == watchtower_id]

        if not matching_pods:
            LOGGER.warning(f"No Watchtower found with identifier {watchtower_id}")
            return {watchtower_id: False}

        deletion_results = {}

        # Attempt to delete each matching pod's deployment
        for pod_name, _ in matching_pods:
            deployment_name = self.get_deployment_name_from_pod_name(pod_name)
            success = self.delete_deployment(deployment_name)

            deletion_results[f"deployment_{deployment_name}"] = success
            
            if success:
                # Remove the pod_name from watchtower_map if the deletion succeeded
                del self.watchtower_map[pod_name]
                LOGGER.info(f"Removed {pod_name} from watchtower map after successful deletion.")
        
        # Delete service if requested
        if cleanup_service:
            service_result = self.delete_watchtower_service()
            deletion_results["service_watchtower-service"] = service_result
        
        # Overall success if at least the deployment deletion succeeded
        deletion_results[watchtower_id] = any(
            v for k, v in deletion_results.items() 
            if k.startswith("deployment_") and v
        )

        LOGGER.info(f"Deletion results for Watchtower {watchtower_id}: {deletion_results}")
        return deletion_results
    
    def delete_all_watchtowers(self, cleanup_service: bool = True) -> Dict[str, Dict[str, bool]]:
        """
        Delete all Watchtower deployments.
        
        Args:
            cleanup_service (bool): Whether to also delete the service (default: True)
            
        Returns:
            Dict[str, Dict[str, bool]]: Deletion results for each Watchtower
        """
        LOGGER.info(f"Deleting all Watchtowers (total: {len(self.watchtower_map)})")
        
        results = {}
        watchtower_ids = list(self.watchtower_map.values())
        
        for watchtower_id in watchtower_ids:
            results[watchtower_id] = self.delete_watchtower_by_id(
                watchtower_id, 
                cleanup_service=(cleanup_service and watchtower_id == watchtower_ids[-1])  # Only cleanup service for last one
            )
        
        return results
    
    # ----- Management Functions -----
    
    def restart_watchtower(self, watchtower_id: str) -> bool:
        """
        Restart a specific Watchtower deployment.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            
        Returns:
            bool: True if restart was successful, False otherwise
        """
        LOGGER.info(f"Restarting Watchtower {watchtower_id}")
        
        # Find pod with matching ID
        pod_name = None
        for pname, wid in self.watchtower_map.items():
            if wid == watchtower_id:
                pod_name = pname
                break
        
        if not pod_name:
            LOGGER.warning(f"No pod found for Watchtower {watchtower_id}")
            return False
        
        deployment_name = self.get_deployment_name_from_pod_name(pod_name)
        
        # Restart deployment using kubectl rollout restart
        cmd = f"kubectl rollout restart deployment/{deployment_name}"
        result = self.run_command(cmd)
        
        if result:
            LOGGER.info(f"Successfully restarted Watchtower {watchtower_id}")
            return True
        else:
            LOGGER.error(f"Failed to restart Watchtower {watchtower_id}")
            return False
    
    def scale_watchtower(self, watchtower_id: str, replicas: int) -> bool:
        """
        Scale a specific Watchtower deployment.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            replicas (int): Number of replicas to scale to
            
        Returns:
            bool: True if scaling was successful, False otherwise
        """
        LOGGER.info(f"Scaling Watchtower {watchtower_id} to {replicas} replicas")
        
        # Find pod with matching ID
        pod_name = None
        for pname, wid in self.watchtower_map.items():
            if wid == watchtower_id:
                pod_name = pname
                break
        
        if not pod_name:
            LOGGER.warning(f"No pod found for Watchtower {watchtower_id}")
            return False
        
        deployment_name = self.get_deployment_name_from_pod_name(pod_name)
        
        # Scale deployment using kubectl scale
        cmd = f"kubectl scale deployment/{deployment_name} --replicas={replicas}"
        result = self.run_command(cmd)
        
        if result:
            LOGGER.info(f"Successfully scaled Watchtower {watchtower_id} to {replicas} replicas")
            return True
        else:
            LOGGER.error(f"Failed to scale Watchtower {watchtower_id}")
            return False
    
    def get_watchtower_events(self, watchtower_id: str) -> Optional[str]:
        """
        Get Kubernetes events for a specific Watchtower.
        
        Args:
            watchtower_id (str): The Watchtower identifier
            
        Returns:
            Optional[str]: Watchtower events or None if not found
        """
        LOGGER.info(f"Getting events for Watchtower {watchtower_id}")
        
        # Find pod with matching ID
        pod_name = None
        for pname, wid in self.watchtower_map.items():
            if wid == watchtower_id:
                pod_name = pname
                break
        
        if not pod_name:
            LOGGER.warning(f"No pod found for Watchtower {watchtower_id}")
            return None
        
        deployment_name = self.get_deployment_name_from_pod_name(pod_name)
        
        # Get events using kubectl get events
        cmd = f"kubectl get events --field-selector involvedObject.name={deployment_name} --sort-by='.lastTimestamp'"
        events = self.run_command(cmd)
        
        if events:
            LOGGER.info(f"Retrieved events for Watchtower {watchtower_id}")
            return events
        else:
            LOGGER.warning(f"No events found for Watchtower {watchtower_id}")
            return None
    
    # ----- Utility Functions -----
    
    def get_deployment_map(self) -> Dict[str, str]:
        """
        Get the current Watchtower deployment map.
        
        Returns:
            Dict[str, str]: Current deployment map (pod_name -> watchtower_id)
        """
        return self.watchtower_map.copy()
    
    def get_watchtower_count(self) -> int:
        """
        Get the total number of deployed Watchtowers.
        
        Returns:
            int: Number of deployed Watchtowers
        """
        return len(self.watchtower_map)