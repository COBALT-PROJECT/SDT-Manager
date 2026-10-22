"""Render the timestamp deployment using only the Python standard library."""
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path


def render(tag="latest", node_port=30012):
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", tag):
        raise ValueError("Invalid image tag")
    if not 30000 <= node_port <= 32767:
        raise ValueError("NodePort must be between 30000 and 32767")
    manifest = Path(__file__).with_name("deployment.yaml").read_text()
    manifest = manifest.replace(
        "docker.io/library/sdt-manager-timestamps:latest",
        f"docker.io/library/sdt-manager-timestamps:{tag}",
    ).replace("nodePort: 30012", f"nodePort: {node_port}")
    # A fresh pod is required even when the same local image tag is reused.
    manifest = manifest.replace(
        "  template:\n    metadata:\n      labels:\n        app: sdt-manager-timestamps",
        "  template:\n    metadata:\n      annotations:\n"
        f'        timestamps.sdt-manager/deployed-at: "{datetime.now(timezone.utc).isoformat()}"\n'
        "      labels:\n        app: sdt-manager-timestamps",
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--node-port", type=int, default=30012)
    args = parser.parse_args()
    try:
        print(render(args.tag, args.node_port), end="")
    except ValueError as exc:
        parser.error(str(exc))
