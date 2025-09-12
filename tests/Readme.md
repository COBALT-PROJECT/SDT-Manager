# SDT-Manager Unit Testing v0.0.1

## Overview

The **SDT-Manager Unit Testing Suite** validates the functionality of the SDT Manager components.  
It ensures correct lifecycle management, integration with Eclipse Ditto, and IDS connector orchestration by testing core modules and APIs.  

The tests are written using **pytest** and are located in the **`unit/`** folder.  
This version of the testing framework includes:

- Unit test coverage for SDT lifecycle management modules  
- Mock-based testing for API endpoints and environment variables  
- Async tests for validating concurrent and distributed behavior  
- Integration checks for Eclipse Ditto and IDS connector logic  

---

## Table of Contents

- [Installation](#installation)  
  - [Prerequisites](#prerequisites)  
  - [Environment Setup](#environment-setup)  
- [Usage](#usage)  
  - [Running Unit Tests](#running-unit-tests)  
  - [Viewing Test Results](#viewing-test-results)   
---

## Installation

### Prerequisites

- Ubuntu 22.04 LTS or later  
- Python **3.10+**  
- `pip` package manager  

### Environment Setup

Step 1: Install Python dependencies for testing:

```bash
pip install -r requirements.txt
```

This installs:

pytest

pytest-mock

requests-mock

pytest-asyncio

Step 2: Verify Installation:

```bash
pytest --version
```
## Usage

### Running Unit Tests

Step 3: Run the unit test

```bash
python3 -m pytest -v
```

### Viewing Test Results

You should see something similar to the logs as in unit_testing_logs.txt