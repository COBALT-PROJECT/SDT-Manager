import subprocess

# Address of containerd
containerd_sock = "/run/k3s/containerd/containerd.sock"

# Images to delete
images = [
    "docker.io/eclipse/ditto-connectivity:latest",
    "docker.io/eclipse/ditto-gateway:latest",
    "docker.io/eclipse/ditto-policies:latest",
    "docker.io/eclipse/ditto-things-search:latest",
    "docker.io/eclipse/ditto-things:latest",
    "docker.io/eclipse/ditto-ui:latest",
    "docker.io/library/mongo:7.0",
    "docker.io/library/nginx:1.27-alpine",
    "docker.io/library/sdt-main-image:latest",
    "docker.io/library/ubuntu:22.04",
    "docker.io/swaggerapi/swagger-ui:v5.9.1",
]

# Function to delete images
def delete_image(image):
    try:
        print(f"Deleting image: {image}")
        subprocess.run(
            ["sudo", "ctr", "--address", containerd_sock, "images", "rm", image],
            check=True,
        )
        print(f"Deleted: {image}")
    except subprocess.CalledProcessError:
        print(f"Failed to delete: {image}")

# Delete all images
for image in images:
    delete_image(image)
