import subprocess
import os

def export_and_import_docker_image_to_k3s(docker_image_name):
    """
    Exports a specific Docker image, saves it as a tar file, and imports it into k3s's containerd runtime.

    :param docker_image_name: Name of the Docker image to export and import (e.g., "sdt-main-image:latest").
    """
    export_dir = "docker2k3s_images"
    k3s_containerd_sock = "/run/k3s/containerd/containerd.sock"

    try:
        # Step 1: Create the export directory
        os.makedirs(export_dir, exist_ok=True)
        print(f"Export directory created: {export_dir}")

        # Step 2: Export the specified Docker image to tar
        image_name = docker_image_name.replace(":", "_").replace("/", "_")
        tar_file = os.path.join(export_dir, f"{image_name}.tar")

        print(f"Exporting {docker_image_name} to {tar_file}...")
        subprocess.run(["sudo", "docker", "save", "-o", tar_file, docker_image_name], check=True)

        print(f"Image {docker_image_name} exported successfully to {tar_file}.")

        # Step 3: Import the tar file into k3s's containerd
        print(f"Importing {tar_file} into k3s's containerd...")
        subprocess.run([
            "sudo", "ctr", "--address", k3s_containerd_sock, "images", "import", tar_file
        ], check=True)

        print(f"Image {docker_image_name} successfully imported into k3s's containerd.")

        # Step 4: Verify the image in k3s's containerd
        print("Verifying images in k3s's containerd...")
        result = subprocess.run([
            "sudo", "ctr", "--address", k3s_containerd_sock, "images", "list"
        ], capture_output=True, text=True, check=True)

        imported_images = result.stdout.strip()

        if docker_image_name.split(":")[0] in imported_images:
            print(f"Image {docker_image_name} is present in k3s's containerd:")
            print(imported_images)
        else:
            print(f"Image {docker_image_name} not found in k3s's containerd.")

        print("Export and import process completed successfully!")

    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Replace with the name of your Docker image
    docker_image_name = "sdt-main-image:latest"

    export_and_import_docker_image_to_k3s(docker_image_name)

