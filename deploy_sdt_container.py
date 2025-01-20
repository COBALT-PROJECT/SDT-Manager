import docker
import time

def start_sdt_container():
    # Initialize Docker client
    client = docker.from_env()

    # Container configuration
    container_name = "sdt-main-container"
    image_name = "sdt-main-image"
    network_name = "docker_default"
    ports = {
        "8000/tcp": 8000,  # Map container's 8000 to host's 8000
        "8005/tcp": 8005,  # Map container's 8005 to host's 8005
    }

    try:
        # Check if the container is already running
        container = client.containers.get(container_name)
        print(f"Container '{container_name}' is already running.")
        return

    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Creating a new one...")

    # Stop and remove any existing container with the same name
    try:
        client.containers.get(container_name).remove(force=True)
        print(f"Removed existing container '{container_name}'.")
    except docker.errors.NotFound:
        pass  # No existing container to remove

    # Create and start the container
    print("Starting the container...")
    container = client.containers.run(
        image_name,
        name=container_name,
        network=network_name,
        ports=ports,
        detach=True,  # Run in detached mode
        remove=False,  # Do not auto-remove
    )

    # Wait and verify
    time.sleep(5)  # Wait for services to initialize
    print(f"Container '{container_name}' is running.")

if __name__ == "__main__":
    start_sdt_container()
