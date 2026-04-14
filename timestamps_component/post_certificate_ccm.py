"""# Basic usage
python post_certificate_ccm.py VEX.json (or SBOM.json)

# With custom options
python post_certificate_ccm.py mydata.json --url http://somehost:8008 --toeid abc-123 --payload-type OTHER
"""

import requests
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="POST JSON data to SDTM adapt API")
    parser.add_argument("file", help="Path to the JSON payload file")
    parser.add_argument("--url", default="http://localhost:8008", help="Base URL (default: http://localhost:8008)")
    parser.add_argument("--toeid", default="123-456", help="TOE ID (default: 123-456)")
    parser.add_argument("--payload-type", default="BOMS", help="Payload type (default: BOMS)")
    args = parser.parse_args()

    endpoint = f"{args.url}/api/SDTM/adapt"
    params = {
        "payload_type": args.payload_type,
        "toeid": args.toeid,
    }
    headers = {
        "Content-Type": "application/json",
    }

    with open(args.file, "r") as f:
        data = f.read()

    response = requests.post(endpoint, params=params, headers=headers, data=data)

    print(f"Status: {response.status_code}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)


if __name__ == "__main__":
    main()