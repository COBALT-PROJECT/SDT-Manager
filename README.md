# SDT-Manager v0.0.1

## Overview

The **SDT-Manager** is responsible for managing the lifecycle of the Security Digital Twin (SDT) and IDS connectors, which are deployed as pods in a Kubernetes cluster of Eclipse Ditto. It's primary function is to orchestrate the information flow between the SDT components and the CCM Manager.

This initial version includes scripts and manifests for:

- Instantiating and deleting SDT pods in a Kubernetes cluster
- Verifying container execution independently (Docker)
- Managing the SDT deployment alongside Eclipse Ditto

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
  - [Ditto Installation](#ditto-installation)
- [Usage](#usage)
  - [Step-by-Step Workflow](#step-by-step-workflow)
  - [Image Management](#image-management)
  - [Pod Verification](#pod-verification)
- [Deletion](#deletion)
- [Combined Deployment](#combined-deployment)

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
- Kubernetes (k3s recommended)
- Eclipse Ditto (clone from [https://github.com/eclipse-ditto/ditto](https://github.com/eclipse-ditto/ditto))

### Environment Setup

To enable Kubernetes CLI in Python scripts, add the following line to your `.bashrc` file:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

### Ditto Installation
Now to setup Eclipse Ditto software, follow the instructions:

Run the command shown below in terminal of Ubuntu VM.

```bash
git clone https://github.com/Engineering-Research-and-Development/true-connector.git

