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
  - [SDT pod lifecycle management](#sdt-pod-lifecycle-management)
  - [IDS connector pods lifecycle management](#ids-connector-pods-lifecycle-management)


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

### SDT pod lifecycle management
NOTE: The API server of the SDT Manager runs on port 8008, the Graphical User Interface (GUI) can be found at 8008/docs/ (http://localhost:8008/docs/)

The API calls can be used for managing the lifecycle of the SDT pods:

Instantiation: 
  - Select the API call of type POST and API endpoint '/deploy'
  NOTE: The SDT is deployed with a hexadecimal identifier which can is rendered in the response of the API call, and can also obtained by performing GET status request.

Get Status:
  - Select the API call of type GET with API endpoint '/deployments'

Send data payload to the SDT Manager (for it to be relayed to the SDT)
  - Select the API call of type POST with the API endpoint '/api/SDT/create' 

Termination:
  - Select the API call of type POST with API endpoint '/delete'
  NOTE: use the identifier of the pod as an input parameter to terminate the SDT pod.

### IDS connector pods lifecycle management
The API calls that can be used to manage the lifecycle of the IDS connector pods are:

Instantiation:
  - Select the API call of type POST with the endpoint '/connector/deploy' and mention if you want a consumer/provider ids connector as the string query of the API call.

Get Status:
  - Select the API call of type GET with the endpoint '/connectors'

Scaling:
  - Select the API call of type POST with the endpoint '/connector/{connector_id}/scale' and mention the number of replica IDS connector pods you desire in the deployment.

Termination:
  - Select the API call of type POST with endpoint '/connector/delete' and provide the connector id as a query string for the API call to delete the desired ids connector pod.

Provider and Consumer Pods synchronization:
  - Go to the ids-sync-service folder and execute build-and-deploy.sh file (read the readme.md file for detailed information on information routing between provider and consumer pods)







