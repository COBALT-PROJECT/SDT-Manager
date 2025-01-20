import os
import subprocess
import argparse
import logging
import time
from kubernetes import client, config

# Constants
WORK_DIR = "/home/allen/ditto"
KUBECTL_PATH = "/usr/local/bin/kubectl"
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"
SDT_YAML_FILE = "/home/allen/k3s-SDT-Ditto/yaml_scripts/sdt-pod-with-ditto-k3s.yaml" #works
#SDT_YAML_FILE="~/deployment/kubernetes/deploymentFiles/sdt-pod-with-ditto-k3s.yaml" #use absolute path to make it work

# Set Kubernetes config explicitly for K3s
os.environ["KUBECONFIG"] = KUBECONFIG_PATH

# Configure Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def run_shell_command(command: str):
    """Executes a shell command and logs output."""
    try:
        if command.startswith("kubectl "):
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
    """Deploys Kubernetes services including MongoDB, Ditto, Swagger UI, and Nginx."""
    logger.info("Deploying Kubernetes Services...")
    deployment_files = {
        "mongodb": "deployment/kubernetes/deploymentFiles/mongodb/mongodb.yaml",
        "ditto-log-files": "deployment/kubernetes/deploymentFiles/ditto/ditto-log-files.yaml",
        "ditto-services": "deployment/kubernetes/deploymentFiles/ditto/",
        "swagger-ui": "deployment/kubernetes/deploymentFiles/swagger/",
        "nginx": "deployment/kubernetes/deploymentFiles/nginx/",
    }
    for service, yaml_path in deployment_files.items():
        run_shell_command(f"kubectl apply -f {yaml_path}")

def wait_for_ditto_pods():
    """Waits for all Ditto pods to be running before proceeding."""
    logger.info("Waiting for all Ditto pods to be in 'Running' state...")
    config.load_kube_config(config_file=KUBECONFIG_PATH)
    v1 = client.CoreV1Api()

    while True:
        pods = v1.list_namespaced_pod(namespace="default").items
        all_running = True
        for pod in pods:
            if pod.metadata.labels and "app" in pod.metadata.labels and "ditto" in pod.metadata.labels["app"]:
                pod_status = pod.status.phase
                logger.info(f"Pod {pod.metadata.name} status: {pod_status}")
                if pod_status != "Running":
                    all_running = False

        if all_running:
            logger.info("All Ditto pods are running.")
            break
        logger.info("Not all Ditto pods are ready. Waiting for 10 seconds before checking again...")
        time.sleep(10)

def deploy_ditto_cluster():
    """Deploys the entire Ditto Kubernetes cluster and waits for completion."""
    logger.info("Starting Ditto Cluster Deployment...")
    create_configmaps()
    deploy_services()
    wait_for_ditto_pods()

    logger.info("Waiting for 120 seconds before deploying SDT Pod...")
    time.sleep(120)

    logger.info("Deploying SDT Pod...")
    run_shell_command(f"kubectl apply -f {SDT_YAML_FILE}")
    logger.info("SDT Pod deployed successfully.")

def main(action: str):
    """Main function to handle CLI arguments."""
    if action == "deploy-ditto-sdt":
        deploy_ditto_cluster()
    else:
        logger.error("Invalid action. Use --help for available options.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Kubernetes Deployments.")
    parser.add_argument(
        "action",
        choices=["deploy-ditto-sdt"],  # New action to deploy Ditto & SDT
        help="Action to perform on the deployment.",
    )
    args = parser.parse_args()
    main(args.action)
