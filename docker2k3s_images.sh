#!/bin/bash

# Define variables
EXPORT_DIR="docker2k3s_images"
K3S_CONTAINERD_SOCK="/run/k3s/containerd/containerd.sock"

# Create the directory to store tar files
mkdir -p $EXPORT_DIR

echo "Export directory created: $EXPORT_DIR"

# Step 1: List all tagged Docker images (exclude dangling images)
DOCKER_IMAGES=$(sudo docker images --filter "dangling=false" --format "{{.Repository}}:{{.Tag}}")

if [ -z "$DOCKER_IMAGES" ]; then
    echo "No tagged Docker images found!"
    exit 1
fi

echo "Docker tagged images found:"
echo "$DOCKER_IMAGES"

# Step 2: Export each tagged Docker image
for IMAGE in $DOCKER_IMAGES; do
    IMAGE_NAME=$(echo "$IMAGE" | sed 's/[:\/]/_/g')  # Replace : and / with _ for the tar file name
    TAR_FILE="$EXPORT_DIR/${IMAGE_NAME}.tar"

    echo "Exporting $IMAGE to $TAR_FILE..."
    sudo docker save -o "$TAR_FILE" "$IMAGE"
    if [ $? -ne 0 ]; then
        echo "Failed to export $IMAGE!"
        exit 1
    fi
done

echo "All Docker tagged images exported to $EXPORT_DIR."

# Step 3: Import images into k3s's Containerd
for TAR_FILE in $EXPORT_DIR/*.tar; do
    echo "Importing $(basename $TAR_FILE) into k3s's Containerd..."
    sudo ctr --address "$K3S_CONTAINERD_SOCK" images import "$TAR_FILE"
    if [ $? -ne 0 ]; then
        echo "Failed to import $TAR_FILE!"
        exit 1
    fi
done

echo "All images successfully imported into k3s's Containerd."

# Step 4: Verify images in k3s's Containerd
echo "Verifying images in k3s's Containerd..."
IMPORTED_IMAGES=$(sudo ctr --address "$K3S_CONTAINERD_SOCK" images list)

if [ -z "$IMPORTED_IMAGES" ]; then
    echo "No images found in k3s's Containerd!"
    exit 1
fi

echo "Images in k3s's Containerd:"
echo "$IMPORTED_IMAGES"

echo "Export and import process completed successfully!"
