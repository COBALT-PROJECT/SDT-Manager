# File: run_deployments.sh
#!/bin/bash

echo "Starting SDT deployment test..."
for i in {1..50}
do
    echo "Running deployment $i of 50"
    python3 sdt_manager.py
    # Wait for 5 seconds between deployments to ensure cleanup
    sleep 5
done
echo "Deployment test completed."

