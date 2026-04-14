import json
import requests
import os
import logging
import time  # <-- add this


from cyclonedx.exception import MissingOptionalDependencyException
from cyclonedx.model.bom import Bom
from cyclonedx.schema import OutputFormat, SchemaVersion
from cyclonedx.validation import make_schemabased_validator
from cyclonedx.validation.json import JsonValidator, JsonStrictValidator


SDT_INTERFACE_HOST = "localhost"
SDT_INTERFACE_PORT = "8001"



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
        print("SDT Manager-Adapter instance created.")

    # def send_to_controller1(self, payload):
    #     # print(payload)
    #     url = 'http://127.0.0.1:8005/api/create1/'
    #     try:
    #         r = requests.post(url, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
    #         return r

    #         #session = requests.Session()
    #         #session.auth = ("ditto", "ditto")
    #         #r = session.post("http://10.0.1.174:8080/api/2/things/", json=payload, headers={'Content-Type': 'application/json'})

    #     except Exception as e:
    #         print(e)
    #     return

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
        url = 'http://'+ SDT_INTERFACE_HOST +':'+ SDT_INTERFACE_PORT + '/api/SDT/create/'
        print(url)
        params = {'toeid': toeid, 'payload_type': payload_type,   'appmap': 'true'}
        print(type(payload))

        # Validate inputs
        if not isinstance(payload, dict):
            logger.error("Invalid payload type: expected dict, got %s", type(payload).__name__)
            return None
            
        try:
            logger.info(f"Sending request to {url} with params {params}")
            r = requests.post(
                url, 
                data=json.dumps(payload), 
                params=params, 
                headers={'Content-Type': 'application/json','X-AppMap-Recording': 'true','X-Correlation-Id': str(int(time.time() * 1000)),},
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


    # def validate_cyclone(self, cyclone_content):
    #     """
    #     Validates a CycloneDX payload.

    #     Args:
    #         cyclone_content (dict): The parsed JSON content of the CycloneDX payload.

    #     Returns:
    #         bool: True if the payload is valid, False otherwise.
    #     """
    #     logger = logging.getLogger(__name__)
        
    #     # Check if the payload has the required fields
    #     if "bomFormat" in cyclone_content and "specVersion" in cyclone_content and "serialNumber" in cyclone_content:
    #         logger.info("Basic CycloneDX format validation passed")
    #         return True

    #     my_json_validator = JsonStrictValidator(SchemaVersion.V1_4)
    #     try:
    #         json_data = json.dumps(cyclone_content)
    #         validation_errors = my_json_validator.validate_str(json_data)
    #         if validation_errors:
    #             logger.info('JSON invalid\nValidationError: %s', repr(validation_errors))
    #             sys.exit(2)
    #         logger.info('JSON valid')
    #     except MissingOptionalDependencyException as error:
    #         logger.info('JSON-validation was skipped due to %s', error)
    #     bom_from_json = Bom.from_json(json_loads(json_data))
    #     logger.info('bom_from_json %s', repr(bom_from_json))

    #     return False

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


    # def from_cyclone(self, cyclone_json):
    #     """
    #     Transforms a CycloneDX payload (JSON string) conforming to the 1.6 schema from any BOM type 
    #     (CBOM, SBOM, SaaSBOM, VEX, VDR, HBOM, etc.) into a unified structure with attributes and features,
    #     including every detail present in the input.
        
    #     Args:
    #         cyclone_json (str): The JSON string of the CycloneDX BOM.
        
    #     Returns:
    #         str: A JSON string representing the transformed CycloneDX BOM in a standardized format with full details.
    #     """
    #     logger = logging.getLogger(__name__)
    #     logger.info("Starting transformation of CycloneDX payload")
        
    #     # Parse the JSON input
    #     cyclone_content = json.loads(cyclone_json)
    #     # logger.info("Successfully parsed CycloneDX JSON")
    #     # print(cyclone_content)
    #     # Extract metadata (if available) and its component information
    #     metadata = cyclone_content.get("metadata", {})
        

    #     # logger.info(f"Converted serial number: {convert_serial_number}")

    #     # Set up the attributes section based on CycloneDX 1.6, including full metadata
    #     # Extract all top-level fields that should be in attributes (those that come before metadata)
    #     attributes = {}
        
    #     # Include any other top-level fields that aren't metadata, components, services, etc.
    #     for key in cyclone_content:
    #         if key not in ["metadata", "components", "services", "dependencies", 
    #               "compositions", "vulnerabilities", "formulations", 
    #               "annotations", "definitions", "declarations", "extensions"]:
    #             attributes[key] = cyclone_content[key]
        
    #     # Initialize features dictionary
    #     features = {}

    #     # Process metadata
    #     if metadata:
    #         features["metadata"] = {
    #             "properties": metadata
    #         }
    #         # logger.info("Added metadata to features")
        
    #     components = cyclone_content.get("components", [])
    #     if components:
    #         component_properties = {}
    #         for idx, component in enumerate(components, 1):
    #             component_properties[str(idx)] = component
            
    #         features["components"] = {
    #         "properties": component_properties
    #         }
        
    #     dependencies = cyclone_content.get("dependencies", [])
    #     if dependencies:
    #         dependency_properties = {}
    #         for idx, dependency in enumerate(dependencies, 1):
    #             dependency_properties[str(idx)] = dependency
            
    #         features["dependencies"] = {
    #         "properties": dependency_properties
    #         }
        
    #     services = cyclone_content.get("services", [])
    #     if services:
    #         service_properties = {}
    #         for idx, service in enumerate(services, 1):
    #             service_properties[str(idx)] = service
            
    #         features["services"] = {
    #         "properties": service_properties
    #         }

    #     compositions = cyclone_content.get("compositions", [])
    #     if compositions:
    #         composition_properties = {}
    #         for idx, composition in enumerate(compositions, 1):
    #             composition_properties[str(idx)] = composition
            
    #         features["compositions"] = {
    #         "properties": composition_properties
    #         }

    #     vulnerabilities = cyclone_content.get("vulnerabilities", [])
    #     if vulnerabilities:
    #         vulnerability_properties = {}
    #         for idx, vulnerability in enumerate(vulnerabilities, 1):
    #             vulnerability_properties[str(idx)] = vulnerability
            
    #         features["vulnerabilities"] = {
    #         "properties": vulnerability_properties
    #         }

    #     formulations = cyclone_content.get("formulations", [])
    #     if formulations:
    #         formulation_properties = {}
    #         for idx, formulation in enumerate(formulations, 1):
    #             formulation_properties[str(idx)] = formulation
            
    #         features["formulations"] = {
    #         "properties": formulation_properties
    #         }

    #     annotations = cyclone_content.get("annotations", [])
    #     if annotations:
    #         annotation_properties = {}
    #         for idx, annotation in enumerate(annotations, 1):
    #             annotation_properties[str(idx)] = annotation
            
    #         features["annotations"] = {
    #         "properties": annotation_properties
    #         }

    #     definitions = cyclone_content.get("definitions", [])
    #     if definitions:
    #         definition_properties = {}
    #         for idx, definition in enumerate(definitions, 1):
    #             definition_properties[str(idx)] = definition
            
    #         features["definitions"] = {
    #         "properties": definition_properties
    #         }

    #     declarations = cyclone_content.get("declarations", [])
    #     if declarations:
    #         declaration_properties = {}
    #         for idx, declaration in enumerate(declarations, 1):
    #             declaration_properties[str(idx)] = declaration
            
    #         features["declarations"] = {
    #         "properties": declaration_properties
    #         }

    #     extensions = cyclone_content.get("extensions", [])
    #     if extensions:
    #         extension_properties = {}
    #         for idx, extension in enumerate(extensions, 1):
    #             extension_properties[str(idx)] = extension
            
    #         features["extensions"] = {
    #         "properties": extension_properties
    #         }
        
    #     # Create the unified structure, including the full raw input for reference
    #     transformed_cyclone = {
    #         "attributes": attributes,
    #         "features": features,
    #         "_metadata": cyclone_content
    #     }
        
    #     # Return the transformed structure as a JSON string
    #     logger.info("Successfully transformed CycloneDX payload")
    #     print(type(transformed_cyclone))
    #     return transformed_cyclone

    
    def from_oscal_component(self, oscal_json, thing_id=None):
        """
        Transforms an OSCAL Component Definition into a Thing structure.
        
        Args:
            oscal_json (str): The JSON string of the OSCAL component definition.
            thing_id (str): Optional custom thing ID.
        
        Returns:
            dict: A dictionary representing the transformed OSCAL component.
        """
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of OSCAL Component Definition")
        
        oscal_content = json.loads(oscal_json)
        component_definition = oscal_content.get("component-definition", {})
        
        # Extract metadata
        metadata = component_definition.get("metadata", {})
        
        # Set up attributes - similar to your cyclone approach
        attributes = {}
        for key in component_definition:
            if key not in ["metadata", "components", "capabilities", "back-matter"]:
                attributes[key] = component_definition[key]
        
        # Add source type identifier
        attributes["sourceType"] = "oscal-component"
        attributes["source"] = "CCM"  # Added: Source is CCM (Cobalt Component Manager) via adapter
        # attributes["thingId"] = thing_id or self._generate_thing_id("oscal", attributes)
        
        # Initialize features
        features = {}
        
        # Process metadata
        if metadata:
            features["metadata"] = {"properties": metadata}
        
        # Process components
        components = component_definition.get("components", [])
        if components:
            component_properties = {}
            for idx, component in enumerate(components, 1):
                component_properties[str(idx)] = component
            features["components"] = {"properties": component_properties}
        
        # Process capabilities
        capabilities = component_definition.get("capabilities", [])
        if capabilities:
            capability_properties = {}
            for idx, capability in enumerate(capabilities, 1):
                capability_properties[str(idx)] = capability
            features["capabilities"] = {"properties": capability_properties}
        
        # Process back-matter
        back_matter = component_definition.get("back-matter", {})
        if back_matter:
            features["back_matter"] = {"properties": back_matter}
        
        transformed_oscal = {
            "attributes": attributes,
            "features": features,
            "_metadata": oscal_content,
            "_relationships": self._extract_oscal_relationships(component_definition)
        }
        
        logger.info("Successfully transformed OSCAL component definition")
        return transformed_oscal
    
    def from_arm_template(self, arm_json, thing_id=None):
        """
        Transforms an ARM Template into a Thing structure.
        
        Args:
            arm_json (str): The JSON string of the ARM template.
            thing_id (str): Optional custom thing ID.
        
        Returns:
            dict: A dictionary representing the transformed ARM template.
        """
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of ARM Template")
        
        arm_content = json.loads(arm_json)
        
        # Set up attributes - following your pattern
        attributes = {}
        for key in arm_content:
            if key not in ["metadata", "parameters", "variables", "resources", "outputs"]:
                attributes[key] = arm_content[key]
        
        # Add source type identifier
        attributes["sourceType"] = "arm-template"
        attributes["source"] = "CCM"  # Added: Source is CCM (Cobalt Component Manager) via adapter
        # attributes["thingId"] = thing_id or self._generate_thing_id("arm", attributes)
        
        # Initialize features
        features = {}
        
        # Process ARM template sections
        parameters = arm_content.get("parameters", {})
        if parameters:
            features["parameters"] = {"properties": parameters}
        
        variables = arm_content.get("variables", {})
        if variables:
            features["variables"] = {"properties": variables}
        
        resources = arm_content.get("resources", [])
        if resources:
            resource_properties = {}
            for idx, resource in enumerate(resources, 1):
                resource_properties[str(idx)] = resource
            features["resources"] = {"properties": resource_properties}
        
        outputs = arm_content.get("outputs", {})
        if outputs:
            features["outputs"] = {"properties": outputs}
        
        transformed_arm = {
            "attributes": attributes,
            "features": features,
            "_metadata": arm_content,
            "_relationships": self._extract_arm_relationships(arm_content)
        }
        
        logger.info("Successfully transformed ARM template")
        return transformed_arm
    
    # def from_cyclone(self, cyclone_json, thing_id=None):
    #     """
    #     Enhanced version of your existing from_cyclone method with thing_id support.
    #     """
    #     logger = logging.getLogger(__name__)
    #     logger.info("Starting transformation of CycloneDX payload")
        
    #     # Your existing cyclone transformation logic...
    #     cyclone_content = json.loads(cyclone_json)
        
    #     # Extract attributes (your existing logic)
    #     attributes = {}
    #     for key in cyclone_content:
    #         if key not in ["metadata", "components", "services", "dependencies", 
    #                       "compositions", "vulnerabilities", "formulations", 
    #                       "annotations", "definitions", "declarations", "extensions"]:
    #             attributes[key] = cyclone_content[key]
        
    #     # Add source type and thing ID
    #     attributes["sourceType"] = "cyclonedx"
    #     attributes["thingId"] = thing_id or self._generate_thing_id("cyclonedx", attributes)
        
    #     # Your existing features logic...
    #     features = {}
        
    #     # Process all sections (your existing code)
    #     if cyclone_content.get("metadata"):
    #         features["metadata"] = {"properties": cyclone_content["metadata"]}
        
    #     # ... rest of your existing feature processing logic ...
        
    #     transformed_cyclone = {
    #         "attributes": attributes,
    #         "features": features,
    #         "_metadata": cyclone_content,
    #         "_relationships": self._extract_cyclonedx_relationships(cyclone_content)
    #     }
        
    #     logger.info("Successfully transformed CycloneDX payload")
    #     return transformed_cyclone


    
    def from_cyclone(self, cyclone_json, thing_id=None):
        """
        Transforms a CycloneDX payload (JSON string) conforming to the 1.6 schema from any BOM type 
        (CBOM, SBOM, SaaSBOM, VEX, VDR, HBOM, etc.) into a unified Thing structure with attributes and features,
        including every detail present in the input.
        
        Args:
            cyclone_json (str): The JSON string of the CycloneDX BOM.
            thing_id (str): Optional custom thing ID.
        
        Returns:
            dict: A dictionary representing the transformed CycloneDX BOM in Thing format with full details.
        """
        import uuid
        from datetime import datetime
        
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of CycloneDX payload")
        
        # Parse the JSON input
        cyclone_content = json.loads(cyclone_json)
        metadata = cyclone_content.get("metadata", {})
    
        # Set up attributes section - core Thing identity
        attributes = {}
        
        # Include top-level fields in attributes (Thing identity)
        for key in cyclone_content:
            if key not in ["metadata", "components", "services", "dependencies", 
                          "compositions", "vulnerabilities", "formulations", 
                          "annotations", "definitions", "declarations", "extensions"]:
                attributes[key] = cyclone_content[key]
        
        # Add Thing-specific metadata
        attributes["sourceType"] = "cyclonedx"
        attributes["source"] = "CCM"  # Added: Source is CCM (Cobalt Component Manager) via adapter
        # attributes["thingId"] = thing_id or self._generate_thing_id("cyclonedx", attributes)
        attributes["transformedAt"] = datetime.utcnow().isoformat() + "Z"
        attributes["bomType"] = self.detect_bom_type(cyclone_content)
        
        # Extract component name and version from metadata for Thing identity
        if metadata.get("component"):
            attributes["componentName"] = metadata["component"].get("name")
            attributes["componentVersion"] = metadata["component"].get("version")
        
        # Initialize features dictionary - Thing capabilities/data
        features = {}
    
        # Process all CycloneDX sections as features
        sections_to_process = [
            "metadata", "components", "services", "dependencies", 
            "compositions", "vulnerabilities", "formulations", 
            "annotations", "definitions", "declarations", "extensions"
        ]
        
        for section in sections_to_process:
            section_data = cyclone_content.get(section)
            if section_data:
                if isinstance(section_data, list):
                    # For arrays, create indexed properties
                    section_properties = {}
                    for idx, item in enumerate(section_data, 1):
                        # Use meaningful IDs when available
                        item_id = self._extract_item_id(item, section, idx)
                        section_properties[item_id] = item
                    
                    features[section] = {"properties": section_properties}
                else:
                    # For objects, store directly
                    features[section] = {"properties": section_data}
                
                logger.info(f"Processed {section}: {len(section_properties) if isinstance(section_data, list) else 1} items")
    
        # Create the unified Thing structure
        transformed_cyclone = {
            "attributes": attributes,
            "features": features,
            "_metadata": cyclone_content,  # Keep original for reference
            "_relationships": self._extract_cyclonedx_relationships(cyclone_content),
            "_schema": {
                "version": "1.0",
                "source": "cyclonedx",
                "specVersion": cyclone_content.get("specVersion", "1.6")
            }
        }
        
        logger.info("Successfully transformed CycloneDX payload to Thing")
        return transformed_cyclone
    
    def _extract_item_id(self, item, section, fallback_idx):
        """Extract meaningful ID from items based on section type."""
        if section == "components":
            # Use bom-ref, purl, or name for components
            return (item.get("bom-ref") or 
                    item.get("purl") or 
                    f"{item.get('name', 'component')}-{fallback_idx}")
        elif section == "vulnerabilities":
            # Use vulnerability ID
            return item.get("id", f"vuln-{fallback_idx}")
        elif section == "services":
            # Use service name or bom-ref
            return (item.get("bom-ref") or 
                    item.get("name") or 
                    f"service-{fallback_idx}")
        elif section == "dependencies":
            # Use ref for dependencies
            return item.get("ref", f"dep-{fallback_idx}")
        else:
            # Default to section-index pattern
            return f"{section}-{fallback_idx}"
    
    # def _generate_thing_id(self, source_type, attributes):
    #     """Generate a unique thing ID based on source type and content."""
    #     import hashlib
        
    #     # Use serialNumber for CycloneDX (most reliable)
    #     if source_type == "cyclonedx" and "serialNumber" in attributes:
    #         # Clean up the serial number for use as ID
    #         serial = attributes["serialNumber"]
    #         # Remove urn: prefix if present
    #         if serial.startswith("urn:"):
    #             serial = serial[4:]
    #         return f"cyclonedx-{serial}"
    #     else:
    #         # Generate based on content hash
    #         content_str = json.dumps(attributes, sort_keys=True)
    #         base_id = hashlib.sha256(content_str.encode()).hexdigest()[:12]
    #         return f"{source_type}-{base_id}"
    
    def _extract_cyclonedx_relationships(self, cyclone_content):
        """Extract comprehensive relationships from CycloneDX BOM."""
        relationships = []
        
        # Component dependencies
        dependencies = cyclone_content.get("dependencies", [])
        for dependency in dependencies:
            ref = dependency.get("ref")
            depends_on = dependency.get("dependsOn", [])
            
            for dep in depends_on:
                relationships.append({
                    "source": ref,
                    "target": dep,
                    "type": "depends_on",
                    "relationship": "component-dependency"
                })
        
        # Component vulnerabilities
        vulnerabilities = cyclone_content.get("vulnerabilities", [])
        for vuln in vulnerabilities:
            vuln_id = vuln.get("id")
            affects = vuln.get("affects", [])
            
            for affect in affects:
                ref = affect.get("ref")
                if ref and vuln_id:
                    relationships.append({
                        "source": ref,
                        "target": vuln_id,
                        "type": "has_vulnerability",
                        "relationship": "component-vulnerability"
                    })
        
        # Service dependencies
        services = cyclone_content.get("services", [])
        for service in services:
            service_ref = service.get("bom-ref")
            dependencies = service.get("dependencies", [])
            
            for dep in dependencies:
                if service_ref:
                    relationships.append({
                        "source": service_ref,
                        "target": dep,
                        "type": "depends_on",
                        "relationship": "service-dependency"
                    })
        
        return relationships
    
    # def _generate_thing_id(self, source_type, attributes):
    #     """Generate a unique thing ID based on source type and content."""
    #     import hashlib
    #     import uuid
        
    #     # Use serialNumber for CycloneDX, uuid for OSCAL, or generate based on content
    #     if source_type == "cyclonedx" and "serialNumber" in attributes:
    #         base_id = attributes["serialNumber"]
    #     elif source_type == "oscal" and "uuid" in attributes:
    #         base_id = attributes["uuid"]
    #     else:
    #         # Generate based on content hash
    #         content_str = json.dumps(attributes, sort_keys=True)
    #         base_id = hashlib.sha256(content_str.encode()).hexdigest()[:12]
        
    #     return f"{source_type}-{base_id}"
    
    def _extract_oscal_relationships(self, component_definition):
        """Extract relationships from OSCAL component definition."""
        relationships = []
        
        components = component_definition.get("components", [])
        for component in components:
            component_uuid = component.get("uuid")
            
            # Extract control implementations
            control_implementations = component.get("control-implementations", [])
            for impl in control_implementations:
                source_uuid = impl.get("source")
                if source_uuid:
                    relationships.append({
                        "source": component_uuid,
                        "target": source_uuid,
                        "type": "implements",
                        "relationship": "control-implementation"
                    })
        
        return relationships
    
    def _extract_arm_relationships(self, arm_content):
        """Extract relationships from ARM template."""
        relationships = []
        
        resources = arm_content.get("resources", [])
        for resource in resources:
            resource_name = resource.get("name")
            depends_on = resource.get("dependsOn", [])
            
            for dependency in depends_on:
                relationships.append({
                    "source": resource_name,
                    "target": dependency,
                    "type": "depends_on",
                    "relationship": "resource-dependency"
                })
        
        return relationships
    
    # def _extract_cyclonedx_relationships(self, cyclone_content):
    #     """Extract relationships from CycloneDX BOM."""
    #     relationships = []
        
    #     dependencies = cyclone_content.get("dependencies", [])
    #     for dependency in dependencies:
    #         ref = dependency.get("ref")
    #         depends_on = dependency.get("dependsOn", [])
            
    #         for dep in depends_on:
    #             relationships.append({
    #                 "source": ref,
    #                 "target": dep,
    #                 "type": "depends_on",
    #                 "relationship": "component-dependency"
    #             })
        
    #     return relationships
    
    def process_multiple_files(self, file_configs):
        """
        Process multiple files and create separate Things with cross-references.
        
        Args:
            file_configs (list): List of dicts with 'path', 'type', and optional 'thing_id'
        
        Returns:
            dict: Dictionary of thing_id -> transformed_thing
        """
        logger = logging.getLogger(__name__)
        things = {}
        
        for config in file_configs:
            file_path = config['path']
            file_type = config['type']
            thing_id = config.get('thing_id')
            
            try:
                with open(file_path, 'r') as f:
                    file_content = f.read()
                
                if file_type.lower() == 'cyclonedx':
                    thing = self.from_cyclone(file_content, thing_id)
                elif file_type.lower() == 'oscal':
                    thing = self.from_oscal_component(file_content, thing_id)
                elif file_type.lower() == 'arm':
                    thing = self.from_arm_template(file_content, thing_id)
                else:
                    logger.error(f"Unsupported file type: {file_type}")
                    continue
                
                # Use filename as key if thingId is disabled
                things[file_path] = thing
                logger.info(f"Processed {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {str(e)}")
        
        # Add cross-references between things
        self._add_cross_references(things)
        
        return things
    
    def _add_cross_references(self, things):
        """Add cross-references between different thing types."""
        logger = logging.getLogger(__name__)
        
        # Find related things based on naming patterns or content
        cyclonedx_things = {k: v for k, v in things.items() if v['attributes'].get('sourceType') == 'cyclonedx'}
        oscal_things = {k: v for k, v in things.items() if v['attributes'].get('sourceType') == 'oscal-component'}
        arm_things = {k: v for k, v in things.items() if v['attributes'].get('sourceType') == 'arm-template'}
        
        # Add cross-references to each thing
        for thing_id, thing in things.items():
            cross_refs = []
            
            # OSCAL things can govern CycloneDX things
            if thing['attributes'].get('sourceType') == 'oscal-component':
                for cyclone_id in cyclonedx_things.keys():
                    cross_refs.append({
                        "target": cyclone_id,
                        "relationship": "governs",
                        "type": "compliance"
                    })
            
            # ARM things can deploy CycloneDX things
            if thing['attributes'].get('sourceType') == 'arm-template':
                for cyclone_id in cyclonedx_things.keys():
                    cross_refs.append({
                        "target": cyclone_id,
                        "relationship": "deploys",
                        "type": "deployment"
                    })
            
            if cross_refs:
                thing['_cross_references'] = cross_refs
                logger.info(f"Added {len(cross_refs)} cross-references to {thing_id}")


    def detect_bom_type(self, cyclone_content):
        """
        Detects the BOM type from the CycloneDX content.

        Args:
            cyclone_content (dict): The parsed JSON content of the CycloneDX payload.

        Returns:
            str: The detected BOM type.
        """
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
                    return "sbom"
                elif component.get("type") == "device":
                    return "hbom"
        elif "dependencies" in cyclone_content and "services" in cyclone_content:
            return "saasbom"
        elif "vulnerabilities" in cyclone_content:
            return "vex"
        else:
            return "boms"

    def convert_urn(self, input_str):
        parts = input_str.split(":", 2)  # Split into max 3 parts
        if len(parts) == 3:
            return f"{parts[0]}.{parts[1]}:{parts[2]}"
        return input_str  # Return original if format is unexpected


    