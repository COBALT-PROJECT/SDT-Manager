#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "http://localhost:8008/api/SDTM/adapt"
DEFAULT_SBOM_PATH = Path(__file__).resolve().parents[1] / "SBOM.json"


def post_sbom(endpoint: str, sbom_path: Path) -> int:
    with sbom_path.open("rb") as file_handle:
        payload = file_handle.read()

    # Validate locally so a bad file fails before the request is sent.
    json.loads(payload.decode("utf-8"))

    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(f"Status: {response.status}")
            if body:
                print(body)
            return 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Status: {exc.code}")
        if body:
            print(body)
        return 1
    except URLError as exc:
        print(f"Request failed: {exc.reason}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Post SBOM.json to the SDTM adapter endpoint.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"Adapter endpoint URL. Default: {DEFAULT_ENDPOINT}")
    parser.add_argument("--sbom", type=Path, default=DEFAULT_SBOM_PATH, help=f"SBOM JSON path. Default: {DEFAULT_SBOM_PATH}")
    args = parser.parse_args()

    return post_sbom(args.endpoint, args.sbom)


if __name__ == "__main__":
    raise SystemExit(main())
