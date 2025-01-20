import os
import subprocess
import argparse
import logging

# Constants
WORK_DIR = "/home/allen/ditto"  # Ensure this is the correct working directory
KUBECTL_PATH = "/usr/local/bin/kubectl"  # Ensure this matches your system
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"  # K3s kubeconfig path

# Set Kubernetes config explicitly for K3s
os.environ["KUBECONFIG"] = KUBECONFIG_PATH

# Configure Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def run_shell_command(command: str):
    """Executes a shell command with correct environment settings."""
    try:
        os.environ["KUBECONFIG"] = KUBECONFIG_PATH

        # Fix double 'kubectl' prefix issue
        if command.startswith("kubectl "):  # Ensure there's a space
            command = command.replace("kubectl ", f"{KUBECTL_PATH} ", 1)

        logger.info(f"Executing in {WORK_DIR}: {command}")

        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, cwd=WORK_DIR)
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        logger.error(e.stderr)

def create_configmaps():
    """Creates Kubernetes ConfigMaps."""
    logger.info("Creating ConfigMaps...")
    configmap_files = {
        "nginx-conf": "deployment/kubernetes/deploymentFiles/nginx/nginx.conf",
        "nginx-cors": "deployment/kubernetes/deploymentFiles/nginx/nginx-cors.conf",
        "nginx-htpasswd": "deployment/kubernetes/deploymentFiles/nginx/nginx.htpasswd",
        "nginx-index": "deployment/kubernetes/deploymentFiles/nginx/index.html",
        "swagger-ui-api": "documentation/src/main/resources/openapi",
    }

    for name, file_path in configmap_files.items():
        run_shell_command(f"kubectl create configmap {name} --from-file={file_path}")

def deploy_services():
    """Deploys Kubernetes services including MongoDB, Ditto, PostgreSQL, and Keycloak."""
    logger.info("Deploying Kubernetes Services...")
    deployment_files = {
        "mongodb": "deployment/kubernetes/deploymentFiles/mongodb/mongodb.yaml",
        "ditto-log-files": "deployment/kubernetes/deploymentFiles/ditto/ditto-log-files.yaml",
        "ditto-services": "deployment/kubernetes/deploymentFiles/ditto/",
        "swagger-ui": "deployment/kubernetes/deploymentFiles/swagger/",
        "nginx": "deployment/kubernetes/deploymentFiles/nginx",
        #"postgresql": "deployment/kubernetes/deploymentFiles/postgres/",
        #"keycloak": "deployment/kubernetes/deploymentFiles/keycloak/",
    }

    for service, yaml_path in deployment_files.items():
        run_shell_command(f"kubectl apply -f {yaml_path}")

def deploy_ditto_cluster():
    """Deploys the entire Ditto Kubernetes cluster."""
    logger.info("Starting Ditto Cluster Deployment...")
    create_configmaps()
    deploy_services()
    logger.info("Ditto Cluster Deployment Completed.")

def main(action: str):
    """Main function to handle CLI arguments."""
    if action == "deploy-ditto":
        deploy_ditto_cluster()
    else:
        logger.error("Invalid action. Use --help for available options.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Kubernetes Deployments.")
    parser.add_argument(
        "action",
        choices=["deploy-ditto"],  # This script is only meant for deployment of k3s cluster of ndt
        help="Action to perform on the deployment.",
    )
    args = parser.parse_args()
    main(args.action)
