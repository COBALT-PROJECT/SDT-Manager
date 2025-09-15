# File: adapter.py
import json
import requests
import os

from cyclonedx.exception import MissingOptionalDependencyException
from cyclonedx.model.bom import Bom
from cyclonedx.schema import OutputFormat, SchemaVersion
from cyclonedx.validation import make_schemabased_validator
from cyclonedx.validation.json import JsonValidator, JsonStrictValidator


SDT_INTERFACE_HOST = "localhost" # Default, can be overridden by environment variables
SDT_INTERFACE_PORT = "30008"  # Default, can be overridden by environment variables

import logging

class DTModelAdapter():
    """
    A class implementing the adapter to translate different data models to the SDT Thing Model(Eclipse Ditto).

    ...
    Attributes
    ----------
    None
    Methods
    -------
    __init__(self)

    send_to_controller(payload)
        Sends the payload to the controller.
    validate_cyclone(cyclone_content)
        Validates a CycloneDX payload.
    validate_cyclonedx_smart(payload, strict=False, thorough=True)
        Smart validation of a CycloneDX BOM that combines quick field checking and schema validation.
    from_cyclone(cyclone_json, name)
        converts the cycloneDX payload to a unified structure of Thing with attributes and features.
        
    """


    def __init__(self):
        """
        Initialize the DTModelAdapter with host and port possibly from environment variables.
        """
        self.logger = logging.getLogger(__name__)
        # Allow configuration through environment variables
        self.host = os.environ.get('SDT_INTERFACE_HOST', SDT_INTERFACE_HOST)
        self.port = os.environ.get('SDT_INTERFACE_PORT', SDT_INTERFACE_PORT)
        self.logger.info(f"SDT Manager-Adapter instance created with host={self.host}, port={self.port}")

    def send_to_controller(self, payload, toeid="123456789", payload_type="BOMS"):
        """
        Sends the payload to the controller.
        
        Args:
            payload (dict): The payload to send to the controller.
            toeid (str): Target of Evaluation ID. Default is "123456789".
            payload_type (str): Type of payload (AI or QDT). Default is "BOMS".
            
        Returns:
            requests.Response: The response from the controller or None if an error occurs.
        """
        logger = logging.getLogger(__name__)
        url = f'http://{self.host}:{self.port}/api/SDT/create/'
        logger.info(f"Sending payload to controller at URL: {url}")
        params = {'toeid': toeid, 'payload_type': payload_type}
        logger.info(f"Request parameters: {params}")

        # Validate inputs
        if not isinstance(payload, dict):
            logger.error(f"Invalid payload type: expected dict, got {type(payload).__name__}")
            return None
            
        try:
            logger.info(f"Sending request to {url} with params {params}")
            r = requests.post(
                url, 
                data=json.dumps(payload), 
                params=params, 
                headers={'Content-Type': 'application/json'},
                timeout=30  # Add timeout to prevent hanging
            )
            
            # Check for HTTP errors
            r.raise_for_status()
            logger.info(f"Request successful with status code {r.status_code}")
            return r
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error occurred: {e}, status code: {e.response.status_code}")
            return e.response
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error occurred: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timed out: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error occurred: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON encoding error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending to controller: {str(e)}")
        return None

    def validate_cyclonedx_smart(self, payload, strict=False, thorough=True):
        """
        Smart validation of a CycloneDX BOM that combines quick field checking and schema validation.
        Automatically detects the schema version from the payload.
        
        Args:
            payload (str | dict): The JSON payload as a string or a Python dictionary.
            strict (bool): If True, use the strict JSON validator. Default is False.
            thorough (bool): If True, performs complete schema validation. If False, only checks required fields.
        
        Returns:
            bool: True if validation passes, False otherwise.
        """
        logger = logging.getLogger(__name__)
        
        try:
            # Parse the payload if it's a string
            if isinstance(payload, str):
                try:
                    content = json.loads(payload)
                    json_data = payload  # Keep original string for validation
                except json.JSONDecodeError:
                    logger.info("Invalid JSON format in the payload.")
                    return False
            else:
                content = payload
                json_data = json.dumps(payload)
                
            # Quick check for required fields
            if "bomFormat" not in content or "specVersion" not in content or "serialNumber" not in content:
                logger.info("Missing required fields: bomFormat, specVersion, or serialNumber")
                return False
            
            # Get the schema version from the payload
            spec_version = content.get("specVersion", "1.4")  # Default to 1.4 if not specified
            
            # Map the specVersion to a SchemaVersion enum
            schema_version_map = {
                "1.0": SchemaVersion.V1_0,
                "1.1": SchemaVersion.V1_1,
                "1.2": SchemaVersion.V1_2,
                "1.3": SchemaVersion.V1_3,
                "1.4": SchemaVersion.V1_4,
                "1.5": SchemaVersion.V1_5,
                "1.6": SchemaVersion.V1_6
            }
            
            schema_version = schema_version_map.get(spec_version, SchemaVersion.V1_4)
            
            # If only basic validation is requested, return success
            if not thorough:
                logger.info(f"Basic validation passed. Detected schema version: {spec_version}")
                return True
            
            # Perform thorough schema validation
            validator = JsonStrictValidator(schema_version=schema_version) if strict else JsonValidator(schema_version=schema_version)
            
            validation_errors = validator.validate_str(json_data)
            
            if not validation_errors:
                logger.info(f"Validation passed. Schema version: {spec_version}")
                return True
            else:
                logger.info(f"Validation failed with errors: {validation_errors}")
                return False
                
        except Exception as e:
            logger.info(f"An error occurred: {str(e)}")
            return False


    def from_cyclone(self, cyclone_json, hash_value=None):
        """
        Transforms a CycloneDX payload (JSON string) conforming to the 1.6 schema from any BOM type 
        (CBOM, SBOM, SaaSBOM, VEX, VDR, HBOM, etc.) into a unified structure with attributes and features,
        including every detail present in the input.
        
        Args:
            cyclone_json (str): The JSON string of the CycloneDX BOM.
        
        Returns:
            dict: A dictionary representing the transformed CycloneDX BOM in a standardized format with full details.
        """
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of CycloneDX payload")
        
        # Parse the JSON input
        try:
            cyclone_content = json.loads(cyclone_json)
            logger.info("Successfully parsed CycloneDX JSON")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise ValueError(f"Invalid JSON in CycloneDX payload: {e}")
        
        # Extract metadata (if available) and its component information
        metadata = cyclone_content.get("metadata", {})
        
        # Set up the attributes section based on CycloneDX 1.6, including full metadata
        # Extract all top-level fields that should be in attributes (those that come before metadata)
        attributes = {}
        
          # Add the hash if provided
        if hash_value is not None:
            attributes["BOMhash"] = hash_value

        # Include any other top-level fields that aren't metadata, components, services, etc.
        for key in cyclone_content:
            if key not in ["metadata", "components", "services", "dependencies", 
                  "compositions", "vulnerabilities", "formulations", 
                  "annotations", "definitions", "declarations", "extensions"]:
                attributes[key] = cyclone_content[key]
        
        # Initialize features dictionary
        features = {}

        # Process metadata
        if metadata:
            features["metadata"] = {
                "properties": metadata
            }
            logger.info("Added metadata to features")
        
        # Process each section of the CycloneDX payload
        sections = [
            "components", "dependencies", "services", "compositions", 
            "vulnerabilities", "formulations", "annotations", 
            "definitions", "declarations", "extensions"
        ]
        
        for section in sections:
            section_items = cyclone_content.get(section, [])
            if section_items:
                section_properties = {}
                for idx, item in enumerate(section_items, 1):
                    section_properties[str(idx)] = item
                
                features[section] = {
                    "properties": section_properties
                }
                logger.info(f"Added {section} to features with {len(section_items)} items")
        
        # Create the unified structure, including the full raw input for reference
        transformed_cyclone = {
            "attributes": attributes,
            "features": features,
            "_metadata": {
                "original_bom_type": self.detect_bom_type(cyclone_content),
                "transformation_timestamp": self._get_timestamp()
            }
        }
        
        # Return the transformed structure
        logger.info("Successfully transformed CycloneDX payload")
        return transformed_cyclone

    def _get_timestamp(self):
        """Get the current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'  # Z denotes UTC

    def detect_bom_type(self, cyclone_content):
        """
        Detects the BOM type from the CycloneDX content.

        Args:
            cyclone_content (dict): The parsed JSON content of the CycloneDX payload.

        Returns:
            str: The detected BOM type.
        """
        self.logger.info("Detecting BOM type from CycloneDX content")
        
        if "components" in cyclone_content:
            components = cyclone_content.get("components", [])
            for component in components:
                if component.get("type") == "cryptographic-asset":
                    if component.get("cryptoProperties", {}).get("assetType") == "algorithm":
                        n="cbom.algorithm"
                        if "dependencies" in cyclone_content:
                            return n + ".dependencies"
                        else:
                            return n
                    elif component.get("cryptoProperties", {}).get("assetType") == "certificate":
                        n = "cbom.certificate"
                        if "dependencies" in cyclone_content:
                            return n + ".dependencies"
                        else:
                            return n
                elif component.get("type") == "library":
                    self.logger.info("Detected SBOM type")
                    return "sbom"
                elif component.get("type") == "device":
                    self.logger.info("Detected HBOM type")
                    return "hbom"
        elif "dependencies" in cyclone_content and "services" in cyclone_content:
            self.logger.info("Detected SaaSBOM type")
            return "saasbom"
        elif "vulnerabilities" in cyclone_content:
            self.logger.info("Detected VEX type")
            return "vex"
        else:
            self.logger.info("Default BOM type: boms")
            return "boms"

    def convert_urn(self, input_str):
        """
        Converts a URN to a dot-notation format.
        
        Args:
            input_str (str): The input URN string.
            
        Returns:
            str: The converted string in dot-notation format.
        """
        parts = input_str.split(":", 2)  # Split into max 3 parts
        if len(parts) == 3:
            return f"{parts[0]}.{parts[1]}:{parts[2]}"
        return input_str  # Return original if format is unexpected