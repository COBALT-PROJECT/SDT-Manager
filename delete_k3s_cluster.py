import os
import subprocess
import logging
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

# Constants
WORK_DIR = "/home/allen/ditto"  # Ensure this is the correct working directory
KUBECTL_PATH = "/usr/local/bin/kubectl"  # Ensure this matches your system
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"  # K3s kubeconfig path

# Set Kubernetes config explicitly for K3s (or else kubectl won't work)
os.environ["KUBECONFIG"] = KUBECONFIG_PATH

# Configure Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_correct_directory():
    """Ensures the script is run from the correct directory."""
    if os.getcwd() != WORK_DIR:
        logger.error(f"Please run this script from the {WORK_DIR} directory.")
        exit(1)

def run_shell_command(command: str):
    """Executes a shell command and logs output."""
    try:
        # Ensure the correct kubectl path is used
        if command.startswith("kubectl "):
            command = command.replace("kubectl ", f"{KUBECTL_PATH} ", 1)

        logger.info(f"Executing in {WORK_DIR}: {command}")
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, cwd=WORK_DIR)
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        logger.error(e.stderr)

def delete_configmaps():
    """Deletes all Ditto-related ConfigMaps."""
    logger.info("Deleting ConfigMaps...")
    configmaps = ["nginx-conf", "nginx-cors", "nginx-htpasswd", "nginx-index", "swagger-ui-api"]
    run_shell_command(f"kubectl delete configmap {' '.join(configmaps)} --ignore-not-found")

def delete_ditto_resources():
    """Deletes all Ditto-related resources."""
    logger.info("Deleting MongoDB resources...")
    run_shell_command("kubectl delete -f deployment/kubernetes/deploymentFiles/mongodb/mongodb.yaml --ignore-not-found")

    logger.info("Deleting Ditto log files pod...")
    run_shell_command("kubectl delete -f deployment/kubernetes/deploymentFiles/ditto/ditto-log-files.yaml --ignore-not-found")

    logger.info("Deleting Ditto core services...")
    run_shell_command("kubectl delete -f deployment/kubernetes/deploymentFiles/ditto/ --ignore-not-found")

    logger.info("Deleting Swagger UI resources...")
    run_shell_command("kubectl delete -f deployment/kubernetes/deploymentFiles/swagger/swagger.yaml --ignore-not-found")

    logger.info("Deleting Nginx resources...")
    run_shell_command("kubectl delete -f deployment/kubernetes/deploymentFiles/nginx/nginx.yaml --ignore-not-found")

def delete_all_remaining_resources():
    """Deletes all remaining resources in the 'default' namespace."""
    logger.info("Deleting all remaining resources in the default namespace...")
    run_shell_command("kubectl delete all --all -n default --ignore-not-found")

def confirm_deletion():
    """Lists remaining resources in the 'default' namespace."""
    logger.info("Checking for remaining resources in the default namespace...")
    run_shell_command("kubectl get all -n default")

def main():
    """Main function to delete all Ditto resources in the default namespace."""
    ensure_correct_directory()
    logger.info("Starting Ditto Cluster Deletion Process...")
    delete_configmaps()
    delete_ditto_resources()
    delete_all_remaining_resources()
    confirm_deletion()
    logger.info("Ditto Cluster Cleanup Completed.")

if __name__ == "__main__":
    main()
