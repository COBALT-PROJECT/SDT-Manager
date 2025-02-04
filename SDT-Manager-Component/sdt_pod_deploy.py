# File: sdt_pod_deploy.py
import subprocess
import time
import logging
import uuid

YAML_PATH = "/home/allen/k3s-SDT-Ditto/yaml_scripts/"

class SDTDeployer:
    def __init__(self):
        """Initialize SDTDeployer with logging and pod tracking."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.pod_map = {}  # Store deployed pod names mapped to IDs
        self.logger = logging.getLogger(__name__)
    
    def run_command(self, command):
        """Runs a shell command and returns the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            self.logger.info(result.stdout)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {command}")
            self.logger.error(e.stderr)
            return None
    
    def deploy_pod(self):
        """Deploys the SDT pod and assigns a random identifier."""
        pod_id = uuid.uuid4().hex[:8]  # Generate a short hexadecimal identifier
        self.logger.info(f"Deploying SDT pod with ID: {pod_id}")
        self.run_command(f"kubectl apply -f {YAML_PATH}sdt-pod-with-ditto-k3s.yaml")
        time.sleep(5)  # Give time for pod to be created
        pod_name = self.get_pod_name()
        if pod_name:
            self.pod_map[pod_name] = pod_id  # Store the pod name and ID mapping
            self.logger.info(f"Mapped Pod Name: {pod_name} to ID: {pod_id}")
            self.logger.info(f"Current Pod Map: {self.pod_map}")
    
    def get_pod_name(self):
        """Retrieves the name of the deployed SDT pod."""
        return self.run_command("kubectl get pods -l app=sdt -o jsonpath='{.items[0].metadata.name}'")
    
    def check_pod_running(self):
        """Checks if the SDT pod is running."""
        self.logger.info("Checking if SDT pod is running...")
        for _ in range(30):  # Wait up to ~5 minutes total
            output = self.run_command("kubectl get pods -l app=sdt -o jsonpath='{.items[0].status.phase}'")
            if output and "Running" in output:
                self.logger.info("SDT pod is running.")
                return True
            time.sleep(10)
        self.logger.error("SDT pod did not start running within the expected time.")
        return False
    
    def deploy_service(self):
        """Deploys the SDT service."""
        self.logger.info("Deploying SDT service...")
        self.run_command(f"kubectl apply -f {YAML_PATH}sdt-service.yaml")
