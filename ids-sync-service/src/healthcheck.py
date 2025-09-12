#!/usr/bin/env python3
"""
Health check script for IDS Sync Service container
Used by Docker HEALTHCHECK and Kubernetes probes
"""

import requests
import sys
import os

def check_health():
    """Check if the sync service is healthy"""
    try:
        health_port = os.getenv('HEALTH_PORT', '8080')
        response = requests.get(f'http://localhost:{health_port}/health', timeout=5)
        
        if response.status_code == 200:
            health_data = response.json()
            status = health_data.get('status', 'unknown')
            
            if status in ['healthy', 'starting']:
                print(f"✅ Service is {status}")
                return True
            else:
                print(f"❌ Service status: {status}")
                return False
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

if __name__ == "__main__":
    if check_health():
        sys.exit(0)
    else:
        sys.exit(1)