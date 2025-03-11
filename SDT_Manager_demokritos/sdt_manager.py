#sdt_manager.py
import logging
import subprocess
import csv
import time
from datetime import datetime
from sdt_pod_deploy import SDTDeployer
from delete_sdt_deployment import SDTDeploymentCleaner

class SDTManager:
    def __init__(self):
        """Initialize SDTManager with instances of SDTDeployer and SDTDeploymentCleaner."""
        self.deployer = SDTDeployer()
        self.cleaner = SDTDeploymentCleaner()
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.csv_file = 'sdt_demokritos_create_time.csv'
        self._init_csv()

    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        try:
            with open(self.csv_file, 'x', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Identifier', 'Pod Name', 'Time Taken (seconds)'])
        except FileExistsError:
            pass

    def _log_deployment_time(self, identifier, pod_name, time_taken):
        """Log deployment timing information to CSV file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, identifier, pod_name, f"{time_taken:.2f}"])
    
    def deploy(self):
        """Deploys the SDT pod and service, tracking deployment time."""
        start_time = time.time()
        self.deployer.deploy_pod()
        
        if self.deployer.check_pod_running():
            self.deployer.deploy_service()
            end_time = time.time()
            time_taken = end_time - start_time

            # Get the latest deployment info
            if self.deployer.pod_map:
                pod_name, identifier = next(iter(self.deployer.pod_map.items()))
                self._log_deployment_time(identifier, pod_name, time_taken)
                self.logger.info(f"Total deployment time: {time_taken:.2f} seconds")
        else:
            self.logger.error("Service deployment skipped because the pod is not running.")

    def delete_sdt_deployment_by_id(self, identifier: str) -> dict:
        """
        Delete a specific deployment by its identifier without user interaction.
        
        Args:
            identifier (str): The identifier of the deployment to delete
            
        Returns:
            Dict[str, bool]: Dictionary mapping identifier to deletion success status
        """
        pod_map = self.deployer.pod_map
        if not pod_map:
            return {identifier: False}
        
        pod_name = None
        for name, pod_id in pod_map.items():
            if pod_id == identifier:
                pod_name = name
                break
                
        if not pod_name:
            return {identifier: False}
            
        deployment_name = self.cleaner.get_deployment_name_from_pod_name(pod_name)
        success = self.cleaner.delete_deployment(deployment_name)
        
        if success:
            del self.deployer.pod_map[pod_name]
            self.logger.info(f"Removed {pod_name} from pod map")
            
        return {identifier: success}

    def delete_sdt_deployment(self):
        """
        Shows available deployments and lets user choose which to delete based on identifiers.
        
        Returns:
            Dict[str, bool]: Dictionary mapping identifier to deletion success status
        """
        pod_map = self.deployer.pod_map
        if not pod_map:
            return {}
        
        deletion_results = self.cleaner.cleanup_deployment_by_identifier(pod_map)
        
        for identifier, success in deletion_results.items():
            if success:
                pods_to_remove = [pod_name for pod_name, pod_id in self.deployer.pod_map.items() 
                                if pod_id == identifier]
                for pod_name in pods_to_remove:
                    del self.deployer.pod_map[pod_name]
                    
        return deletion_results

if __name__ == "__main__":
    manager = SDTManager()
    manager.deploy()
    deletion_results = manager.delete_sdt_deployment()
    for identifier, success in deletion_results.items():
        print(f"Deployment deletion for identifier {identifier}: {'Successful' if success else 'Failed'}")
