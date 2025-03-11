# File: delete_sdt_deployment.py
import subprocess
import logging
import re
from typing import Dict, Optional, List

class SDTDeploymentCleaner:
    def __init__(self):
        """Initialize the SDT deployment cleaner with logging configuration."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def run_command(self, command: str) -> Optional[str]:
        """Execute a kubectl command and return the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {command}")
            self.logger.error(f"Error output: {e.stderr}")
            return None

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
            self.logger.debug(f"Extracted deployment name '{deployment_name}' from pod '{pod_name}'")
            return deployment_name
            
        # Fallback: if pattern not found, return the original name
        self.logger.warning(f"Could not extract deployment name from pod '{pod_name}', using as is")
        return pod_name

    def show_available_deployments(self, pod_map: Dict[str, str]) -> Dict[str, str]:
        """
        Display all available deployments and their identifiers.
        
        Args:
            pod_map (Dict[str, str]): Dictionary mapping pod names to their identifiers
            
        Returns:
            Dict[str, str]: Dictionary mapping identifiers to deployment names
        """
        identifier_to_deployment = {}
        
        print("\nAvailable Deployments:")
        print("----------------------")
        for pod_name, identifier in pod_map.items():
            deployment_name = self.get_deployment_name_from_pod_name(pod_name)
            identifier_to_deployment[identifier] = deployment_name
            print(f"Identifier: {identifier} -> Deployment: {deployment_name}")
        
        return identifier_to_deployment

    def get_user_choice(self, valid_identifiers: List[str]) -> Optional[str]:
        """
        Get user input for which deployment to delete.
        
        Args:
            valid_identifiers (List[str]): List of valid identifier choices
            
        Returns:
            Optional[str]: Chosen identifier or None if invalid/cancelled
        """
        while True:
            choice = input("\nEnter the identifier of the deployment to delete (or 'q' to quit): ").strip()
            
            if choice.lower() == 'q':
                return None
                
            if choice in valid_identifiers:
                confirm = input(f"Are you sure you want to delete the deployment with identifier {choice}? (y/n): ")
                if confirm.lower() == 'y':
                    return choice
                print("Deletion cancelled.")
                return None
            
            print(f"Invalid identifier. Please choose from: {', '.join(valid_identifiers)}")

    def delete_deployment(self, deployment_name: str) -> bool:
        """Delete a deployment using kubectl delete command."""
        cmd = f"kubectl delete deployment {deployment_name}"
        result = self.run_command(cmd)
        
        if result is not None:
            self.logger.info(f"Successfully deleted deployment: {deployment_name}")
            return True
        else:
            self.logger.error(f"Failed to delete deployment: {deployment_name}")
            return False

    def cleanup_deployment_by_identifier(self, pod_map: Dict[str, str]) -> Dict[str, bool]:
        """
        Show available deployments and let user choose which to delete (interactive).
        
        Args:
            pod_map (Dict[str, str]): Dictionary mapping pod names to their identifiers
            
        Returns:
            Dict[str, bool]: Dictionary with single identifier mapped to deletion success status
        """
        identifier_to_deployment = self.show_available_deployments(pod_map)
        
        if not identifier_to_deployment:
            self.logger.warning("No deployments found in pod map.")
            return {}
        
        chosen_identifier = self.get_user_choice(list(identifier_to_deployment.keys()))
        
        if not chosen_identifier:
            return {}
        
        deployment_name = identifier_to_deployment[chosen_identifier]
        success = self.delete_deployment(deployment_name)
        
        return {chosen_identifier: success}

def main():
    """Example usage of the SDTDeploymentCleaner class."""
    # Example pod_map (this would normally come from SDTDeployer)
    example_pod_map = {
        "sdt-deployment-6b46d87fc-qpmgt": "12345678"
    }
    
    cleaner = SDTDeploymentCleaner()
    results = cleaner.cleanup_deployment_by_identifier(example_pod_map)
    
    for identifier, success in results.items():
        print(f"Deployment cleanup for identifier {identifier}: {'Successful' if success else 'Failed'}")

if __name__ == "__main__":
    main()
