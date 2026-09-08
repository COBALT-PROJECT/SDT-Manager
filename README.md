# SDT-Manager v0.0.1

## Overview

The **SDT-Manager** is responsible for managing the lifecycle of the Security Digital Twin (SDT) and IDS connectors, which are deployed as pods in a Kubernetes cluster of Eclipse Ditto. Its primary function is to orchestrate the information flow between the SDT components and the CCM Manager.

This version of the SDT Manager includes scripts and manifests for:

- Lifecycle management of SDT pods in a Ditto Kubernetes cluster
- Lifecycle management of Watchtower pods
- Wallet-driven OAuth2 authentication and SQLite-backed credential storage
- Verifying container execution independently (Docker Compose)
- Deployment as a pod inside the same k3s cluster it manages
- Managing the SDT deployment alongside Eclipse Ditto
- Managing the lifecycle of IDS connector pods in the same namespace as Ditto and SDT pods

## Table of Contents

- [Repository structure](#repository-structure)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [Running locally (virtual environment)](#running-locally-virtual-environment)
- [Features](#features)
  - [API endpoint reference](#api-endpoint-reference)
  - [SDT pod lifecycle management](#sdt-pod-lifecycle-management)
  - [IDS connector pods lifecycle management](#ids-connector-pods-lifecycle-management)
  - [Authentication APIs](#authentication-apis)
  - [System status APIs](#system-status-apis)
  - [SDT adapter APIs](#sdt-adapter-apis)
  - [CCMLedger forwarding](#ccmledger-forwarding)
- [Containerization](#containerization)
  - [Docker Compose (standalone)](#docker-compose-standalone)
  - [Kubernetes pod deployment](#kubernetes-pod-deployment)
  - [Deleting the pod](#deleting-the-pod)
  - [Kubernetes resource reference](#kubernetes-resource-reference)
  - [Port reference](#port-reference)

---

## Repository structure

```
SDT-Manager/
├── SDT-Manager/                   # Application source code
│   ├── main.py                    # Entry point
│   ├── sdt_manager_core.py        # Core orchestrator
│   ├── sdt_manager_interface.py   # FastAPI NBI (port 8008)
│   ├── sdt_lifecycle_manager.py   # SDT pod lifecycle via kubectl
│   ├── sdt_connector_manager.py   # IDS connector lifecycle
│   ├── ids_connector.py           # IDS connector kubectl operations
│   ├── watchtower_manager.py      # Watchtower lifecycle via kubectl
│   ├── sdt_authentication_manager.py  # Wallet registration + OAuth2
│   ├── sdt_credential_store.py    # SQLite credential store
│   ├── adapter_all_v2.py          # CycloneDX -> DT Thing adapter (v2)
│   ├── template.json              # Evidence collector routing config
│   ├── requirements.txt           # Python dependencies
│   ├── .env                       # Local environment configuration
│   ├── Dockerfile                 # Container image definition
│   ├── docker-compose.yml         # Standalone Docker Compose deployment
│   ├── deploy.sh                  # Build image + deploy to k3s cluster
│   ├── delete.sh                  # Tear down pod and all k8s resources
│   └── build.sh                   # Build image and import into k3s only
├── yaml_scripts/                  # Kubernetes manifests
│   ├── sdt-manager-k8s.yaml       # Full SDT-Manager k8s deployment
│   ├── sdt-pod-with-ditto-k3s-itr2.yaml  # SDT pod deployment
│   ├── sdt-service.yaml           # SDT NodePort service
│   ├── watchtower-deployment.yaml # Watchtower deployment
│   └── watchtower-service.yaml    # Watchtower service
├── ids-sync-service/              # IDS provider-consumer sync service
├── tests/                         # Unit tests
├── timestamps_component/          # Performance tracking variant
├── SDTM.yaml                      # OpenAPI 3.0 specification (v2.0.0)
└── README.md
```

---

## Installation

### Prerequisites

- Ubuntu 22.04 LTS or later
- Docker and Docker Compose

```bash
sudo apt install docker.io -y
sudo apt install docker-compose -y
```

- Kubernetes (k3s recommended)

```bash
curl -sfL https://get.k3s.io | sh -

# Verify k3s is installed
sudo k3s kubectl get nodes

# Confirm k3s service is running
sudo systemctl status k3s

# Start k3s if not running
sudo systemctl start k3s
```

- Eclipse Ditto (clone from https://github.com/eclipse-ditto/ditto)

```bash
git clone https://github.com/eclipse-ditto/ditto.git

# Verify pods are running
kubectl get pods -n default
kubectl get configmaps -n default
kubectl get svc -n default
```

- IDS connector setup (TrueConnector)

```bash
git clone https://github.com/Engineering-Research-and-Development/true-connector.git

# Verify containers are running
sudo docker-compose up -d
```

Deploy Eclipse Ditto into k3s:

```bash
cp deploy_ditto.py ~/ditto
cd ~/ditto
python3 deploy_ditto.py deploy-ditto
```

### Environment Setup

Export the k3s kubeconfig so `kubectl` works from the shell:

```bash
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
source ~/.bashrc
```

Give your user ownership of the kubeconfig:

```bash
sudo chown $(id -u):$(id -g) /etc/rancher/k3s/k3s.yaml
```

---

## Usage

### Running locally (virtual environment)

Step 1: Create and activate a virtual environment.

```bash
python3 -m venv sdtm-venv
source sdtm-venv/bin/activate
```

Step 2: Install dependencies.

```bash
pip install -r SDT-Manager/requirements.txt
```

Step 3: Run the application.

```bash
cd SDT-Manager/SDT-Manager
python3 main.py
```

The API server starts on `http://localhost:8008`. To exit the virtual environment run `deactivate`.

---

## Features

### API endpoint reference

The SDT Manager API server runs on port `8008` by default. Interactive OpenAPI documentation is available at:

```
http://localhost:8008/docs
```

### SDT pod lifecycle management

Deploy an SDT instance:

```
POST /api/SDTM/digital-twin
```

Deploys the SDT pod and service, deploys the IDS-SDT connector, discovers or deploys Watchtower, and starts the wallet/token authentication flow in a background thread. The response includes the generated `identifier`, plus `ids_connector_id`, `watchtower_id`, and `auth_status`.

Delete an SDT instance:

```
DELETE /api/SDTM/digital-twin/{twinId}
```

Deletes the SDT deployment, linked IDS-SDT connector, linked Watchtower, wallet registration, and all credential records for the SDT and its linked components.

Retrieve one SDT instance:

```
GET /api/SDTM/digital-twin/{twinId}
```

Returns pod state, deployment name, pod IP, node name, readiness, metadata timestamps, authentication status, and linked component authentication status.

List current SDT deployments:

```
GET /api/SDTM/deployments
```

Returns all SDT deployments currently tracked by the running SDT Manager process.

### IDS connector pods lifecycle management

Deploy an IDS connector:

```
POST /connector/deploy?connector_type=ids_sdt
```

The `connector_type` query parameter defaults to `ids_sdt`.

Delete an IDS connector:

```
DELETE /connector/delete?cleanup_resources=true
```

Request body:

```json
{
  "identifier": "connector_id"
}
```

The `cleanup_resources` query parameter defaults to `true`.

List current IDS connectors:

```
GET /connectors
```

Get one IDS connector status:

```
GET /connector/{connector_id}
```

### Authentication APIs

Get authentication status for an SDT or linked component:

```
GET /api/SDTM/auth/{twinId}
```

Returns whether a token exists, current credential status, scope, timestamps, and `linked_sdt_id` when the requested ID belongs to a linked component.

List all credential records:

```
GET /api/SDTM/auth
```

Returns credential metadata for SDTs and linked components. Access tokens and secrets are not included in the listing.

### System status APIs

Overall system status:

```
GET /status
```

Returns deployment counts, connector counts, Watchtower count, authentication summary, and system health.

Health check:

```
GET /health
```

Readiness check:

```
GET /ready
```

### SDT adapter APIs

The adapter APIs run on the SDT Manager API server. Do not send adapter payloads directly to port `30008`; that port is the SDT service/controller interface. The manager adapter validates and transforms incoming artifacts, then forwards the transformed Thing payload to the SDT service `/api/SDT/create/` endpoint.

Validate, transform, and send one payload:

```
POST /api/SDTM/adapt?toeid=00000000-0000-0000-0000-000000000000&payload_type=BOMS
```

Supported `payload_type` values:

```
BOMS, cyclonedx, oscal, arm, mud, muds
```

Example:

```bash
curl -X POST "http://localhost:8008/api/SDTM/adapt?payload_type=BOMS" \
  -H "Content-Type: application/json" \
  -d @sample_bom.json
```

Process multiple files:

```
POST /api/SDTM/adapt/multiple/
```

Request body:

```json
{
  "file_configs": [
    {
      "path": "/path/to/artifact.json",
      "type": "BOMS",
      "thing_id": "optional-target-id"
    }
  ]
}
```

Detect CycloneDX BOM type:

```
GET /api/SDTM/adapt/cyclonedx/detect/
```

Validate a CycloneDX payload without conversion:

```
GET /api/SDTM/adapt/cyclonedx/validate/?strict=false&thorough=true
```

### CCMLedger forwarding

The SDT Manager mirrors transformed payloads to CCMLedger as a best-effort side effect after the SDT write succeeds.

Configured endpoint:

```
POST /v1/manufacturer/sbom
```

Request body:

```json
{
  "content": "<JSON-encoded SBOM content>"
}
```

CCMLedger forwarding uses the most recent access token stored by the credential store. To disable during local testing, set `CCMLEDGER_ENABLED=false` in `SDT-Manager/.env`.

### Provider and Consumer Pods synchronization

See `ids-sync-service/Readme.md` for routing between provider and consumer pods. To deploy run `./ids-sync-service/build-and-deploy.sh`.

---

## Containerization

The SDT Manager can be deployed either as a standalone Docker container (for local testing) or as a pod inside the same k3s cluster it manages (production).

All source files, the `Dockerfile`, and the deployment scripts live in `SDT-Manager/SDT-Manager/`.

### Docker Compose (standalone)

Use this for local development and testing when you do not need the SDT-Manager to control a live cluster.

```bash
cd SDT-Manager/SDT-Manager

# Build and start
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop and remove
docker-compose down
```

The `docker-compose.yml` mounts:

| Mount | Container path | Purpose |
|-------|---------------|---------|
| `/etc/rancher/k3s/k3s.yaml` | `/kube/k3s.yaml` (read-only) | Kubeconfig for kubectl |
| `../yaml_scripts` | `/app/yaml_scripts` (read-only) | SDT and Watchtower manifests |
| `/home/ubuntu/true-connector/kubernetes` | `/app/kubernetes` (read-only) | IDS connector manifests |
| `./logs` | `/app/logs` | Persistent log files |
| `./data` | `/app/data` | SQLite credential store |

Environment variables are sourced from `.env`. Edit that file to configure endpoints before starting.

### Kubernetes pod deployment

The SDT-Manager is deployed as a pod in the same k3s cluster alongside Ditto, SDT, Watchtower, and the IDS connectors.

**Step 1: Build the Docker image and import it into k3s.**

```bash
cd SDT-Manager/SDT-Manager
./deploy.sh
```

This single script performs all steps:
1. Builds the Docker image (`sdt-manager:latest`)
2. Imports the image into k3s containerd via `docker save | k3s ctr images import`
3. Applies `yaml_scripts/sdt-manager-k8s.yaml` which creates all Kubernetes resources
4. Waits for the deployment rollout to complete
5. Prints pod/service status and recent logs

The `--no-build` flag skips the Docker build and re-applies the manifests only (useful after editing the YAML):

```bash
./deploy.sh --no-build
```

**Step 2: Verify the pod is running.**

```bash
kubectl get pods -l app=sdt-manager
kubectl get service sdt-manager-service
```

**Step 3: Check logs.**

```bash
kubectl logs -f deployment/sdt-manager-deployment
```

**Accessing the API:**

| Access path | URL |
|-------------|-----|
| From within the cluster | `http://sdt-manager-service:8008` |
| From the node (NodePort) | `http://<node-ip>:30010` |
| Interactive docs | `http://<node-ip>:30010/docs` |

### Deleting the pod

```bash
cd SDT-Manager/SDT-Manager

# Prompts for confirmation before deleting
./delete.sh

# Skip the confirmation prompt
./delete.sh --force
```

The delete script removes all nine Kubernetes resources created by `sdt-manager-k8s.yaml`, waits for the pod to terminate, and confirms that nothing remains. Note that the PVC (and the SQLite credential store it holds) is deleted as part of this operation.

To redeploy after deletion:

```bash
./deploy.sh
```

### Kubernetes resource reference

`yaml_scripts/sdt-manager-k8s.yaml` is a single multi-document file containing all resources:

| Resource | Name | Purpose |
|----------|------|---------|
| ServiceAccount | `sdt-manager-sa` | Pod identity for in-cluster kubectl access |
| ClusterRole | `sdt-manager-role` | Permissions to manage pods, deployments, services, PVCs, configmaps, secrets |
| ClusterRoleBinding | `sdt-manager-rolebinding` | Binds the role to the service account |
| ConfigMap | `sdt-manager-configmap` | All non-sensitive environment variables |
| Secret | `sdt-manager-secret` | `WALLET_CONTROLLER_KEY` and `DIGITAL_TWIN_API_KEY` |
| ConfigMap | `sdt-manager-yaml-scripts` | SDT, Watchtower YAML manifests — mounted at `/app/yaml_scripts/` |
| hostPath volume | `ids-kubernetes` | IDS connector YAML manifests from host at `/home/sdtm/SDTM/IDS-Connector/IDS_connector_SDT/` — mounted read-only at `/app/kubernetes/` |
| PersistentVolumeClaim | `sdt-manager-data-pvc` | 200 Mi volume for `sdt_credentials.db` |
| Deployment | `sdt-manager-deployment` | The SDT-Manager pod |
| Service | `sdt-manager-service` | NodePort 30010 → port 8008 |

The pod uses `imagePullPolicy: Never` because the image is built locally and imported directly into k3s containerd (not pushed to a registry). The `securityContext.fsGroup: 1000` ensures the PVC is writable by the non-root `sdtm` user inside the container.

kubectl inside the pod authenticates to the Kubernetes API using the service account token that k3s auto-mounts at `/var/run/secrets/kubernetes.io/serviceaccount/`. No `KUBECONFIG` environment variable is needed.

### Port reference

| Component | Port | NodePort | Protocol |
|-----------|------|----------|---------|
| SDT API | 8000 | 30008 | HTTP |
| SDT MQTT | 1883 | 30009 | MQTT |
| SDT-Manager API | 8008 | 30010 | HTTP |
| IDS-SDT Connector | 8004 | — (ClusterIP) | HTTP |
| Watchtower HTTP | 8080 | auto-assigned | HTTP |
| Watchtower gRPC | 50051 | auto-assigned | gRPC |
