# SDT-Manager v0.0.1

## Overview

The **SDT-Manager** is responsible for managing the lifecycle of the Security Digital Twin (SDT) and IDS connectors, which are deployed as pods in a Kubernetes cluster of Eclipse Ditto. It's primary function is to orchestrate the information flow between the SDT components and the CCM Manager.

This initial version includes scripts and manifests for:

- Instantiating and deleting SDT pods in a Kubernetes cluster
- Verifying container execution independently (Docker)
- Managing the SDT deployment alongside Eclipse Ditto
- Managing the lifecycle of IDS connector pods in the same namespace of ditto and SDT pods.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [SDT Manager Deployment](#sdt-manager-deployment)

## Features

- **Pod Lifecycle Management**: Launch and terminate SDT pods in a Kubernetes environment
- **Kubernetes Integration**: Interact with k3s and Ditto using `kubectl`
- **Container Testing**: Run SDT components in Docker before deployment
- **Log Inspection**: Monitor SDT activity and verify pipeline execution
- **Automation Scripts**: Deploy full Ditto + SDT cluster with one command

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

##verify if k3s has been installed by running 
sudo k3s kubectl get nodes
##to confirm k3s service is up and running, run:
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

### Environment Setup

To enable Kubernetes CLI in Python scripts, add the following line to your `.bashrc` file:

```bash
sudo nano ~/.bashrc
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

## Usage

### SDT Manager Deployment
To SDT Manager component can be deployed by following the steps shown below:

Step 1: Create a virtual environment for the deployment of the SDT Manager.

```bash
python3 -m venv sdtm-venv
```

Step 2: Install all python packages from the requirements.txt file.

```bash
pip install requirements.txt
```

NOTE: if pip is not installed in the system, run:
```bash
sudo apt install pip -y
```

Step 3:
Run the SDT Manager application
```bash
cd ~/SDT-Manager
python3 main.py
```




