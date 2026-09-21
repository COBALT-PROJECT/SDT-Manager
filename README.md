# SDT-Manager v0.0.1

## Overview

The **SDT-Manager** is responsible for managing the lifecycle of the Security Digital Twin (SDT) and IDS connectors, which are deployed as pods in a Kubernetes cluster of Eclipse Ditto. It's primary function is to orchestrate the information flow between the SDT components and the CCM Manager.

This version of the SDT Manager includes scripts and manifests for:

- Lifecycle management of SDT pods in a ditto kubernetes cluster
- Verifying container execution independently (Docker)
- Managing the SDT deployment alongside Eclipse Ditto
- Managing the lifecycle of IDS connector pods in the same namespace of ditto and SDT pods.

## Table of Contents

- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [SDT Manager Deployment](#sdt-manager-deployment)
- [Features](#features)
  - [API endpoint reference](#api-endpoint-reference)
  - [SDT pod lifecycle management](#sdt-pod-lifecycle-management)
  - [IDS connector pods lifecycle management](#ids-connector-pods-lifecycle-management)
  - [Authentication APIs](#authentication-apis)
  - [System status APIs](#system-status-apis)
  - [SDT adapter APIs](#sdt-adapter-apis)
  - [CCMLedger forwarding](#ccmledger-forwarding)
- [Containerization](#containerization)
  - [SDT Manager containerized deployment and lifecycle management](#deployment)


## Installation

### Prerequisites

- Ubuntu 22.04 LTS or later
- Docker and Docker Compose
Execute the commands
```bash
sudo apt install docker.io -y
sudo apt install docker-compose -y
```
- Kubernetes (k3s recommended)
Execute the command

```bash
curl -sfL https://get.k3s.io | sh -

## verify if k3s has been installed by running 
sudo k3s kubectl get nodes
## to confirm k3s service is up and running, run:
sudo systemctl status k3s 
## if it is not running, run:
sudo systemctl start k3s
```
- Eclipse Ditto (clone from [https://github.com/eclipse-ditto/ditto](https://github.com/eclipse-ditto/ditto))

Now to setup Eclipse Ditto software, follow the instructions:

Run the command shown below in terminal of Ubuntu VM.

```bash
git clone https://github.com/eclipse-ditto/ditto.git
```

Verify if the pods are running by executing the following commands

```bash
kubectl get pods -n=default
kubectl get configmaps -n=default
kubectl get svc -n=default
```
- IDS connector setup (TrueConnector)

First clone the github repository of Trueconnector onto the system, run the following command:

```bash
git clone https://github.com/Engineering-Research-and-Development/true-connector.git
```
verify if the trueconnector containers are deployed by running the command

```bash
sudo docker-compose up -d
```
NOTE: you should a many containers and volumes get instantiated and have status 'running'.

Now to run Eclipse Ditto as a set of pods in a kubernetes cluster, perform the following commands:
```bash
# copy the file deploy_ditto.py into the 'ditto' directory
cp deploy_ditto.py ~/ditto
cd ~/ditto
python3 deploy_ditto.py deploy-ditto
```

### Environment Setup

To enable Kubernetes CLI in Python scripts, add the following line to your `.bashrc` file:

```bash
sudo nano ~/.bashrc
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

To give root user ownership to kubectl, run the following commands

```bash
# to find user group
id -g (e.g: returns 1000)

#to find username
id -u (e.g: returns 1000)

#change ownership to root

sudo chown 1000:1000 /etc/rancher/k3s/k3s.yaml 
```

## Usage

### SDT Manager Deployment
To SDT Manager component can be deployed by following the steps shown below:

Step 1: Create a virtual environment for the deployment of the SDT Manager.

```bash
python3 -m venv sdtm-venv
```
Step 2: activate virtual environment

```bash
source sdtm-venv/bin/activate
```
NOTE: to exit virtual environment

```bash
source ~/.bashrc
```
Step 3: Install all python packages from the requirements.txt file.

```bash
pip install requirements.txt
```

NOTE: if pip is not installed in the system, run:
```bash
sudo apt install pip -y
```

Step 4:
Run the SDT Manager application
```bash
cd ~/SDT-Manager
python3 main.py
```

## Features

### API endpoint reference

The SDT Manager API server runs on port `8008` by default. Interactive OpenAPI documentation is available at:

```text
http://localhost:8008/docs/
```

The base URL for the examples below is:

```text
http://localhost:8008
```

### SDT pod lifecycle management

Deploy an SDT instance:

```text
POST /api/SDTM/digital-twin
```

This deploys the SDT pod and service, deploys the IDS-SDT connector, discovers or deploys Watchtower, and starts the wallet/token authentication flow in a background thread. The response includes the generated `identifier`, plus `ids_connector_id`, `watchtower_id`, and `auth_status`.

Delete an SDT instance:

```text
DELETE /api/SDTM/digital-twin/{twinId}
```

This deletes the SDT deployment, linked IDS-SDT connector, linked Watchtower, wallet registration, and local credential records for the SDT and linked components.

Retrieve one SDT instance:

```text
GET /api/SDTM/digital-twin/{twinId}
```

Returns pod state, deployment name, pod IP, node name, readiness, metadata timestamps, authentication status, and linked component authentication status.

List current SDT deployments:

```text
GET /api/SDTM/deployments
```

Returns all SDT deployments currently tracked by the running SDT Manager process.

### IDS connector pods lifecycle management

Deploy an IDS connector:

```text
POST /connector/deploy?connector_type=ids_sdt
```

The `connector_type` query parameter defaults to `ids_sdt`.

Delete an IDS connector:

```text
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

```text
GET /connectors
```

Get one IDS connector status:

```text
GET /connector/{connector_id}
```

### Authentication APIs

Get authentication status for an SDT or linked component:

```text
GET /api/SDTM/auth/{twinId}
```

Returns whether a token exists, current credential status, scope, timestamps, and `linked_sdt_id` when the requested ID belongs to a linked component.

List all credential records:

```text
GET /api/SDTM/auth
```

Returns credential metadata for SDTs and linked components. Access tokens and secrets are not included in this listing.

### System status APIs

Overall system status:

```text
GET /status
```

Returns deployment counts, connector counts, Watchtower count, authentication summary, and system health.

Health check:

```text
GET /health
```

Readiness check:

```text
GET /ready
```

### MQTT failure reporting

Every API response with a 4xx or 5xx status, every unhandled endpoint
exception, and asynchronous authentication or downstream SDT delivery failure
is reported to MQTT without blocking the API response.

Configuration is maintained in `SDT-Manager/.env`:

| Variable | Value |
|----------|-------|
| `MQTT_FAILURE_REPORTING_ENABLED` | `true` |
| `MQTT_FAILURE_HOST` | `10.163.1.161` |
| `MQTT_FAILURE_PORT` | `1883` |
| `MQTT_COMPONENT_ID` | `sdt-manager-quantum-01` |
| `MQTT_FAILURE_QUEUE_SIZE` | `1000` |
| `MQTT_FAILURE_MAX_RETRIES` | `3` |
| `MQTT_FAILURE_RETRY_DELAY` | `2` seconds |

The reporter loads this `.env` file directly. For Kubernetes, `deploy.sh`
copies only these MQTT settings into the
`sdt-manager-quantum-mqtt-config` ConfigMap before applying the quantum
manifest, keeping the broker address in one source file.

Reports use topic `components/<component-id>/reports`, QoS 1, and are not
retained. Broker failures are logged locally, and credential-like fields are
redacted before publication.

### SDT adapter APIs

The adapter APIs run on the SDT Manager API server. Do not send adapter payloads directly to `localhost:30008`; port `30008` is the SDT service/controller interface. The manager adapter validates and transforms incoming artifacts, then forwards the transformed Thing payload to the SDT service `/api/SDT/create/` endpoint.

Validate, transform, and send one payload:

```text
POST /api/SDTM/adapt?toeid=00000000-0000-0000-0000-000000000000&payload_type=BOMS
```

Supported `payload_type` values are:

```text
BOMS, cyclonedx, oscal, arm, mud, muds
```

The request body is the JSON artifact to validate and transform. The response includes validation details, conversion time, SDT forwarding status, and CCMLedger forwarding status.

Example:

```bash
curl -X POST "http://localhost:8008/api/SDTM/adapt?payload_type=BOMS" \
  -H "Content-Type: application/json" \
  -d @sample_bom.json
```

Process multiple files:

```text
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

```text
GET /api/SDTM/adapt/cyclonedx/detect/
```

This endpoint expects a CycloneDX JSON payload in the request body and returns the detected BOM type and basic payload counts.

Validate a CycloneDX payload without conversion:

```text
GET /api/SDTM/adapt/cyclonedx/validate/?strict=false&thorough=true
```

This endpoint expects a CycloneDX JSON payload in the request body and returns validation results without sending anything to the SDT.

### CCMLedger forwarding

The SDT Manager can mirror transformed payloads to CCMLedger as a best-effort side effect after the SDT write succeeds.

CCMLedger API documentation:

```text
http://cobalt-dlt.cobalt.local:3000/api-docs/
```

Configured CCMLedger endpoint:

```text
POST /v1/manufacturer/sbom
```

Documented request body shape:

```json
{
  "content": "<JSON-encoded SBOM content>"
}
```

CCMLedger forwarding uses the most recent access token stored by the SDT Manager credential store. If forwarding is not needed during local testing, set `CCMLEDGER_ENABLED=false` in `SDT-Manager/.env` before starting `main.py`.

### Provider and Consumer Pods synchronization

Go to the `ids-sync-service` folder and execute `build-and-deploy.sh`. Read the `ids-sync-service/Readme.md` file for detailed information on routing between provider and consumer pods.

## Containerization

### deployment

Follow the steps to build and deploy the SDT Manager as a container:

```bash
cd ~/docker
```

Run the following commands to build and deploy the SDT Manager as a container:

```bash
# Make scripts executable
chmod +x build-and-deploy.sh build.sh deploy.sh cleanup.sh

# Build the image
./build.sh

# Deploy the container  
./deploy.sh

# Stop and cleanup (basic)
./cleanup.sh

# Stop and cleanup everything
./cleanup.sh --all

# Force cleanup without confirmation
./cleanup.sh --all --force
```
NOTE: In the docker-compose.yml file set the paths to mount the volumes of Trueconnector yaml files to enable instantiation, lifecycle management of IDS pods (consumer and provider)












