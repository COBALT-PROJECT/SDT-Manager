import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from performance_http import requests
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator, JsonValidator

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - optional dependency fallback
    Draft202012Validator = None


SDT_INTERFACE_HOST = os.environ.get("SDT_INTERFACE_HOST", "localhost")
SDT_INTERFACE_PORT = os.environ.get("SDT_INTERFACE_PORT", "30008")

# DLT/CCMLedger runtime workflow disabled; former implementation retained below as comments.
# CCMLEDGER_HOST = os.environ.get("CCMLEDGER_HOST", "cobalt-dlt.cobalt.local")
# CCMLEDGER_PORT = os.environ.get("CCMLEDGER_PORT", "3000")
# CCMLEDGER_SBOM_PATH = os.environ.get("CCMLEDGER_SBOM_PATH", "/v1/manufacturer/sbom")
# CCMLEDGER_ENABLED = os.environ.get("CCMLEDGER_ENABLED", "true").lower() in ("1", "true", "yes")
#
#
# def _ccmledger_result(attempted, success, reason, status_code=None, detail=None):
#     return {
#         "attempted": attempted,
#         "success": success,
#         "reason": reason,
#         "status_code": status_code,
#         "detail": detail,
#     }
#
#
# def _forward_to_ccmledger(payload, params=None, access_token=None):
#     """Mirror the outbound SDT payload to CCMLedger as a best-effort side effect."""
#     logger = logging.getLogger(__name__)
#     if not CCMLEDGER_ENABLED:
#         return _ccmledger_result(
#             attempted=False,
#             success=False,
#             reason="disabled",
#         )
#
#     url = f"http://{CCMLEDGER_HOST}:{CCMLEDGER_PORT}{CCMLEDGER_SBOM_PATH}"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Correlation-Id": str(int(time.time() * 1000)),
#         "X-Forwarded-From": "sdt-manager",
#     }
#     if access_token:
#         headers["Authorization"] = f"Bearer {access_token}"
#     else:
#         logger.warning("No Identity Manager access token found in SQLite; skipping CCMLedger forwarding")
#         return _ccmledger_result(
#             attempted=False,
#             success=False,
#             reason="missing_token",
#             detail="No Identity Manager access token found in SQLite",
#         )
#
#     ledger_payload = {"content": json.dumps(payload)}
#
#     try:
#         logger.info("Forwarding payload to CCMLedger at %s", url)
#         response = requests.post(
#             url,
#             data=json.dumps(ledger_payload),
#             params=params or {},
#             headers=headers,
#             timeout=30,
#         )
#         if response.status_code >= 400:
#             logger.error(
#                 "CCMLedger forwarding failed: status=%s body=%s",
#                 response.status_code,
#                 response.text[:500],
#             )
#             return _ccmledger_result(
#                 attempted=True,
#                 success=False,
#                 reason="http_error",
#                 status_code=response.status_code,
#                 detail=response.text[:500],
#             )
#         else:
#             logger.info("CCMLedger forwarding succeeded: status=%s", response.status_code)
#             return _ccmledger_result(
#                 attempted=True,
#                 success=True,
#                 reason="success",
#                 status_code=response.status_code,
#             )
#     except requests.exceptions.RequestException as exc:
#         logger.error("CCMLedger forwarding error: %s", exc)
#         return _ccmledger_result(
#             attempted=True,
#             success=False,
#             reason="request_exception",
#             detail=str(exc),
#         )
#     except Exception as exc:
#         logger.error("Unexpected CCMLedger forwarding error: %s", exc)
#         return _ccmledger_result(
#             attempted=True,
#             success=False,
#             reason="unexpected_exception",
#             detail=str(exc),
#         )


@dataclass
class ValidationIssue:
    path: str
    message: str
    rule: str = "validation"


@dataclass
class ValidationResult:
    valid: bool
    fmt: str
    schema_version: str = ""
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "format": self.fmt,
            "schema_version": self.schema_version,
            "errors": [
                {"path": issue.path, "message": issue.message, "rule": issue.rule}
                for issue in self.errors
            ],
            "warnings": self.warnings,
        }


@dataclass
class FormatSpec:
    canonical: str
    validator: Callable[..., ValidationResult]
    transformer: Callable[..., Dict[str, Any]]
    schema_version: str


class DTModelAdapterV2:
    """Standalone v2 adapter with unified validation, transforms, and controller dispatch."""

    def __init__(self):
        print("SDT Manager-Adapter instance created.")
        self.logger = logging.getLogger(__name__)
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        self._format_registry = self._build_format_registry()

    def _build_format_registry(self) -> Dict[str, FormatSpec]:
        return {
            "boms": FormatSpec(
                canonical="cyclonedx",
                validator=self._validate_cyclonedx,
                transformer=self._transform_cyclonedx,
                schema_version="CycloneDX dynamic",
            ),
            "cyclonedx": FormatSpec(
                canonical="cyclonedx",
                validator=self._validate_cyclonedx,
                transformer=self._transform_cyclonedx,
                schema_version="CycloneDX dynamic",
            ),
            "oscal": FormatSpec(
                canonical="oscal",
                validator=self._validate_oscal,
                transformer=self._transform_oscal,
                schema_version="oscal-component/v1",
            ),
            "arm": FormatSpec(
                canonical="arm",
                validator=self._validate_arm,
                transformer=self._transform_arm,
                schema_version="arm-template/v1",
            ),
            "mud": FormatSpec(
                canonical="mud",
                validator=self._validate_mud,
                transformer=self._transform_mud,
                schema_version="rfc8520/v1",
            ),
            "muds": FormatSpec(
                canonical="mud",
                validator=self._validate_mud,
                transformer=self._transform_mud,
                schema_version="rfc8520/v1",
            ),
        }

    def get_supported_payload_types(self) -> List[str]:
        return sorted(set(self._format_registry.keys()))

    def _normalize_payload_type(self, payload_type: str) -> str:
        return (payload_type or "").strip().lower()

    def validate_payload(
        self,
        payload: Any,
        payload_type: str,
        strict: bool = True,
        thorough: bool = True,
    ) -> ValidationResult:
        payload_type = self._normalize_payload_type(payload_type)
        spec = self._format_registry.get(payload_type)
        if not spec:
            return ValidationResult(
                valid=False,
                fmt=payload_type or "unknown",
                errors=[
                    ValidationIssue(
                        path="payload_type",
                        message=(
                            f"Unsupported payload_type '{payload_type}'. "
                            f"Supported: {', '.join(self.get_supported_payload_types())}"
                        ),
                        rule="supported-format",
                    )
                ],
            )
        return spec.validator(payload, strict=strict, thorough=thorough)

    def transform_payload(self, payload: Any, payload_type: str) -> Dict[str, Any]:
        payload_type = self._normalize_payload_type(payload_type)
        spec = self._format_registry.get(payload_type)
        if not spec:
            raise ValueError(
                f"Unsupported payload_type '{payload_type}'. "
                f"Supported: {', '.join(self.get_supported_payload_types())}"
            )
        return spec.transformer(payload)

    # def send_to_controller(self, payload, toeid="123456789", payload_type="BOMS", access_token=None):  # DLT forwarding removed
    def send_to_controller(self, payload, toeid="123456789", payload_type="BOMS"):
        """Send payload to the SDT controller."""
        logger = logging.getLogger(__name__)
        url = f"http://{SDT_INTERFACE_HOST}:{SDT_INTERFACE_PORT}/api/SDT/create/"
        params = {"toe_id": toeid, "category": payload_type, "appmap": "true"}

        if not isinstance(payload, dict):
            logger.error("Invalid payload type: expected dict, got %s", type(payload).__name__)
            return {
                "sdt_response": None,
#                 "ccmledger": _ccmledger_result(
#                     attempted=False,
#                     success=False,
#                     reason="invalid_payload",
#                     detail=f"expected dict, got {type(payload).__name__}",
#                 ),
            }

        error_detail = None
        try:
            logger.info("Sending request to %s with params %s", url, params)
            response = requests.post(
                url,
                data=json.dumps(payload),
                params=params,
                headers={
                    "Content-Type": "application/json",
                    "X-AppMap-Recording": "true",
                    "X-Correlation-Id": str(int(time.time() * 1000)),
                },
                timeout=30,
            )
            response.raise_for_status()
            logger.info("SDT write confirmed with status code %s", response.status_code)

#             logger.info("Forwarding payload to CCMLedger with params %s", params)
#             ccmledger_result = _forward_to_ccmledger(
#                 payload,
#                 params=params,
#                 access_token=access_token,
#             )

            return {
                "sdt_response": response,
#                 "ccmledger": ccmledger_result,
            }
        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error occurred: %s, status code: %s", exc, exc.response.status_code)
            return {
                "sdt_response": exc.response,
#                 "ccmledger": _ccmledger_result(
#                     attempted=False,
#                     success=False,
#                     reason="sdt_http_error",
#                     status_code=exc.response.status_code if exc.response is not None else None,
#                     detail=exc.response.text[:500] if exc.response is not None else str(exc),
#                 ),
            }
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error occurred: %s", exc)
            error_detail = str(exc)
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out: %s", exc)
            error_detail = str(exc)
        except requests.exceptions.RequestException as exc:
            logger.error("Request error occurred: %s", exc)
            error_detail = str(exc)
        except Exception as exc:
            logger.error("Unexpected error sending to controller: %s", exc)
            error_detail = str(exc)
        return {
            "sdt_response": None,
#             "ccmledger": _ccmledger_result(
#                 attempted=False,
#                 success=False,
#                 reason="sdt_request_exception",
#                 detail=error_detail,
#             ),
        }

    def validate_and_transform(
        self,
        payload: Any,
        payload_type: str,
        strict: bool = True,
        thorough: bool = True,
    ):
        result = self.validate_payload(payload, payload_type, strict=strict, thorough=thorough)
        if not result.valid:
            return result, None
        return result, self.transform_payload(payload, payload_type)

    def validate_cyclonedx_smart(self, payload, strict=False, thorough=True):
        """Validate CycloneDX by required-field checks first, then schema validation when requested."""
        logger = logging.getLogger(__name__)

        try:
            if isinstance(payload, str):
                try:
                    content = json.loads(payload)
                    json_data = payload
                except json.JSONDecodeError:
                    logger.info("Invalid JSON format in the payload.")
                    return False
            else:
                content = payload
                json_data = json.dumps(payload)

            if "bomFormat" not in content or "specVersion" not in content or "serialNumber" not in content:
                logger.info("Missing required fields: bomFormat, specVersion, or serialNumber")
                return False

            spec_version = content.get("specVersion", "1.4")
            schema_version_map = {
                "1.0": SchemaVersion.V1_0,
                "1.1": SchemaVersion.V1_1,
                "1.2": SchemaVersion.V1_2,
                "1.3": SchemaVersion.V1_3,
                "1.4": SchemaVersion.V1_4,
                "1.5": SchemaVersion.V1_5,
                "1.6": SchemaVersion.V1_6,
            }
            schema_version = schema_version_map.get(spec_version, SchemaVersion.V1_4)

            if not thorough:
                logger.info("Basic validation passed. Detected schema version: %s", spec_version)
                return True

            validator = JsonStrictValidator(schema_version=schema_version) if strict else JsonValidator(schema_version=schema_version)
            validation_errors = validator.validate_str(json_data)

            if not validation_errors:
                logger.info("Validation passed. Schema version: %s", spec_version)
                return True

            logger.info("Validation failed with errors: %s", validation_errors)
            return False
        except Exception as exc:
            logger.info("An error occurred: %s", exc)
            return False

    def _validate_cyclonedx(self, payload: Any, strict: bool = True, thorough: bool = True) -> ValidationResult:
        content = self._coerce_payload_to_dict(payload)
        if content is None:
            return ValidationResult(
                valid=False,
                fmt="cyclonedx",
                errors=[ValidationIssue(path="$", message="Payload is not valid JSON", rule="json")],
            )

        valid = self.validate_cyclonedx_smart(content, strict=strict, thorough=thorough)
        if valid:
            return ValidationResult(
                valid=True,
                fmt="cyclonedx",
                schema_version=content.get("specVersion", ""),
            )

        return ValidationResult(
            valid=False,
            fmt="cyclonedx",
            schema_version=content.get("specVersion", ""),
            errors=[
                ValidationIssue(
                    path="$",
                    message="CycloneDX validation failed",
                    rule="cyclonedx-schema",
                )
            ],
        )

    def _validate_oscal(self, payload: Any, strict: bool = True, thorough: bool = True) -> ValidationResult:
        content = self._coerce_payload_to_dict(payload)
        if content is None:
            return ValidationResult(
                valid=False,
                fmt="oscal",
                errors=[ValidationIssue(path="$", message="Payload is not valid JSON", rule="json")],
            )

        schema = self._get_builtin_schema("oscal")
        issues = self._validate_with_jsonschema(content, schema)

        comp_def = content.get("component-definition", {})
        metadata = comp_def.get("metadata", {}) if isinstance(comp_def, dict) else {}
        if thorough and not metadata:
            issues.append(
                ValidationIssue(
                    path="$.component-definition.metadata",
                    message="Missing metadata object",
                    rule="semantic",
                )
            )

        return ValidationResult(
            valid=len(issues) == 0,
            fmt="oscal",
            schema_version="oscal-component/v1",
            errors=issues,
            warnings=self._jsonschema_warnings(),
        )

    def _validate_arm(self, payload: Any, strict: bool = True, thorough: bool = True) -> ValidationResult:
        content = self._coerce_payload_to_dict(payload)
        if content is None:
            return ValidationResult(
                valid=False,
                fmt="arm",
                errors=[ValidationIssue(path="$", message="Payload is not valid JSON", rule="json")],
            )

        schema = self._get_builtin_schema("arm")
        issues = self._validate_with_jsonschema(content, schema)

        if thorough:
            resources = content.get("resources")
            if not isinstance(resources, list):
                issues.append(
                    ValidationIssue(
                        path="$.resources",
                        message="resources must be an array",
                        rule="semantic",
                    )
                )

        return ValidationResult(
            valid=len(issues) == 0,
            fmt="arm",
            schema_version="arm-template/v1",
            errors=issues,
            warnings=self._jsonschema_warnings(),
        )

    def _validate_mud(self, payload: Any, strict: bool = True, thorough: bool = True) -> ValidationResult:
        content = self._coerce_payload_to_dict(payload)
        if content is None:
            return ValidationResult(
                valid=False,
                fmt="mud",
                errors=[ValidationIssue(path="$", message="Payload is not valid JSON", rule="json")],
            )

        schema = self._get_builtin_schema("mud")
        issues = self._validate_with_jsonschema(content, schema)

        mud_block = content.get("ietf-mud:mud", {})
        if thorough and isinstance(mud_block, dict):
            if "mud-url" not in mud_block:
                issues.append(
                    ValidationIssue(
                        path="$.ietf-mud:mud.mud-url",
                        message="Missing mud-url",
                        rule="semantic",
                    )
                )
            if "last-update" not in mud_block:
                issues.append(
                    ValidationIssue(
                        path="$.ietf-mud:mud.last-update",
                        message="Missing last-update",
                        rule="semantic",
                    )
                )

        return ValidationResult(
            valid=len(issues) == 0,
            fmt="mud",
            schema_version="rfc8520/v1",
            errors=issues,
            warnings=self._jsonschema_warnings(),
        )

    def _transform_cyclonedx(self, payload: Any) -> Dict[str, Any]:
        return self.from_cyclone(self._coerce_payload_to_json(payload))

    def _transform_oscal(self, payload: Any) -> Dict[str, Any]:
        return self.from_oscal_component(self._coerce_payload_to_json(payload))

    def _transform_arm(self, payload: Any) -> Dict[str, Any]:
        return self.from_arm_template(self._coerce_payload_to_json(payload))

    def _transform_mud(self, payload: Any) -> Dict[str, Any]:
        return self.from_mud_profile(self._coerce_payload_to_json(payload))

    def from_oscal_component(self, oscal_json, thing_id=None):
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of OSCAL Component Definition")

        oscal_content = json.loads(oscal_json)
        component_definition = oscal_content.get("component-definition", {})
        metadata = component_definition.get("metadata", {})

        attributes = {}
        for key in component_definition:
            if key not in ["metadata", "components", "capabilities", "back-matter"]:
                attributes[key] = component_definition[key]

        attributes["sourceType"] = "oscal-component"
        attributes["source"] = "CCM"
        if thing_id:
            attributes["thingId"] = thing_id

        features = {}
        if metadata:
            features["metadata"] = {"properties": metadata}

        components = component_definition.get("components", [])
        if components:
            component_properties = {}
            for idx, component in enumerate(components, 1):
                component_properties[str(idx)] = component
            features["components"] = {"properties": component_properties}

        capabilities = component_definition.get("capabilities", [])
        if capabilities:
            capability_properties = {}
            for idx, capability in enumerate(capabilities, 1):
                capability_properties[str(idx)] = capability
            features["capabilities"] = {"properties": capability_properties}

        back_matter = component_definition.get("back-matter", {})
        if back_matter:
            features["back_matter"] = {"properties": back_matter}

        transformed_oscal = {
            "attributes": attributes,
            "features": features,
            "_metadata": oscal_content,
            "_relationships": self._extract_oscal_relationships(component_definition),
        }

        logger.info("Successfully transformed OSCAL component definition")
        return transformed_oscal

    def from_arm_template(self, arm_json, thing_id=None):
        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of ARM Template")

        arm_content = json.loads(arm_json)

        attributes = {}
        for key in arm_content:
            if key not in ["metadata", "parameters", "variables", "resources", "outputs"]:
                attributes[key] = arm_content[key]

        attributes["sourceType"] = "arm-template"
        attributes["source"] = "CCM"
        if thing_id:
            attributes["thingId"] = thing_id

        features = {}

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
            "_relationships": self._extract_arm_relationships(arm_content),
        }

        logger.info("Successfully transformed ARM template")
        return transformed_arm

    def from_cyclone(self, cyclone_json, thing_id=None):
        from datetime import datetime

        logger = logging.getLogger(__name__)
        logger.info("Starting transformation of CycloneDX payload")

        cyclone_content = json.loads(cyclone_json)
        metadata = cyclone_content.get("metadata", {})

        attributes = {}
        for key in cyclone_content:
            if key not in [
                "metadata",
                "components",
                "services",
                "dependencies",
                "compositions",
                "vulnerabilities",
                "formulations",
                "annotations",
                "definitions",
                "declarations",
                "extensions",
            ]:
                attributes[key] = cyclone_content[key]

        attributes["sourceType"] = "cyclonedx"
        attributes["source"] = "CCM"
        attributes["transformedAt"] = datetime.utcnow().isoformat() + "Z"
        attributes["bomType"] = self.detect_bom_type(cyclone_content)
        if thing_id:
            attributes["thingId"] = thing_id

        if metadata.get("component"):
            attributes["componentName"] = metadata["component"].get("name")
            attributes["componentVersion"] = metadata["component"].get("version")

        features = {}
        sections_to_process = [
            "metadata",
            "components",
            "services",
            "dependencies",
            "compositions",
            "vulnerabilities",
            "formulations",
            "annotations",
            "definitions",
            "declarations",
            "extensions",
        ]

        for section in sections_to_process:
            section_data = cyclone_content.get(section)
            if section_data:
                if isinstance(section_data, list):
                    section_properties = {}
                    for idx, item in enumerate(section_data, 1):
                        item_id = self._extract_item_id(item, section, idx)
                        section_properties[item_id] = item
                    features[section] = {"properties": section_properties}
                    item_count = len(section_properties)
                else:
                    features[section] = {"properties": section_data}
                    item_count = 1

                logger.info("Processed %s: %s items", section, item_count)

        transformed_cyclone = {
            "attributes": attributes,
            "features": features,
            "_metadata": cyclone_content,
            "_relationships": self._extract_cyclonedx_relationships(cyclone_content),
            "_schema": {
                "version": "1.0",
                "source": "cyclonedx",
                "specVersion": cyclone_content.get("specVersion", "1.6"),
            },
        }

        logger.info("Successfully transformed CycloneDX payload to Thing")
        return transformed_cyclone

    def _extract_item_id(self, item, section, fallback_idx):
        if section == "components":
            return item.get("bom-ref") or item.get("purl") or f"{item.get('name', 'component')}-{fallback_idx}"
        if section == "vulnerabilities":
            return item.get("id", f"vuln-{fallback_idx}")
        if section == "services":
            return item.get("bom-ref") or item.get("name") or f"service-{fallback_idx}"
        if section == "dependencies":
            return item.get("ref", f"dep-{fallback_idx}")
        return f"{section}-{fallback_idx}"

    def _extract_cyclonedx_relationships(self, cyclone_content):
        relationships = []

        dependencies = cyclone_content.get("dependencies", [])
        for dependency in dependencies:
            ref = dependency.get("ref")
            depends_on = dependency.get("dependsOn", [])

            for dep in depends_on:
                relationships.append(
                    {
                        "source": ref,
                        "target": dep,
                        "type": "depends_on",
                        "relationship": "component-dependency",
                    }
                )

        vulnerabilities = cyclone_content.get("vulnerabilities", [])
        for vuln in vulnerabilities:
            vuln_id = vuln.get("id")
            affects = vuln.get("affects", [])

            for affect in affects:
                ref = affect.get("ref")
                if ref and vuln_id:
                    relationships.append(
                        {
                            "source": ref,
                            "target": vuln_id,
                            "type": "has_vulnerability",
                            "relationship": "component-vulnerability",
                        }
                    )

        services = cyclone_content.get("services", [])
        for service in services:
            service_ref = service.get("bom-ref")
            service_dependencies = service.get("dependencies", [])

            for dep in service_dependencies:
                if service_ref:
                    relationships.append(
                        {
                            "source": service_ref,
                            "target": dep,
                            "type": "depends_on",
                            "relationship": "service-dependency",
                        }
                    )

        return relationships

    def _extract_oscal_relationships(self, component_definition):
        relationships = []

        components = component_definition.get("components", [])
        for component in components:
            component_uuid = component.get("uuid")
            control_implementations = component.get("control-implementations", [])
            for implementation in control_implementations:
                source_uuid = implementation.get("source")
                if source_uuid:
                    relationships.append(
                        {
                            "source": component_uuid,
                            "target": source_uuid,
                            "type": "implements",
                            "relationship": "control-implementation",
                        }
                    )

        return relationships

    def _extract_arm_relationships(self, arm_content):
        relationships = []

        resources = arm_content.get("resources", [])
        for resource in resources:
            resource_name = resource.get("name")
            depends_on = resource.get("dependsOn", [])
            for dependency in depends_on:
                relationships.append(
                    {
                        "source": resource_name,
                        "target": dependency,
                        "type": "depends_on",
                        "relationship": "resource-dependency",
                    }
                )

        return relationships

    def from_mud_profile(self, mud_json: str, thing_id: Optional[str] = None) -> Dict[str, Any]:
        content = json.loads(mud_json)
        mud = content.get("ietf-mud:mud", {})

        attributes = {
            "sourceType": "mud",
            "source": "CCM",
            "mudUrl": mud.get("mud-url"),
            "mudVersion": mud.get("mud-version"),
            "lastUpdate": mud.get("last-update"),
        }
        if thing_id:
            attributes["thingId"] = thing_id

        features = {
            "mud": {"properties": mud},
        }
        if "ietf-access-control-list:acls" in content:
            features["acls"] = {
                "properties": content.get("ietf-access-control-list:acls", {})
            }

        return {
            "attributes": attributes,
            "features": features,
            "_metadata": content,
            "_relationships": self._extract_mud_relationships(content),
            "_schema": {
                "version": "1.0",
                "source": "mud",
                "specVersion": "rfc8520",
            },
        }

    def _extract_mud_relationships(self, mud_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        relationships = []
        mud = mud_content.get("ietf-mud:mud", {})
        from_policy = mud.get("from-device-policy", {}).get("access-lists", {}).get("access-list", [])
        to_policy = mud.get("to-device-policy", {}).get("access-lists", {}).get("access-list", [])

        for acl in from_policy:
            name = acl.get("name")
            if name:
                relationships.append(
                    {
                        "source": "device",
                        "target": name,
                        "type": "allows_from_device",
                        "relationship": "mud-policy",
                    }
                )

        for acl in to_policy:
            name = acl.get("name")
            if name:
                relationships.append(
                    {
                        "source": "device",
                        "target": name,
                        "type": "allows_to_device",
                        "relationship": "mud-policy",
                    }
                )

        return relationships

    def process_multiple_files(self, file_configs: List[Dict[str, Any]]):
        logger = logging.getLogger(__name__)
        things = {}

        for config in file_configs:
            file_path = config["path"]
            file_type = self._normalize_payload_type(config["type"])
            thing_id = config.get("thing_id")

            try:
                with open(file_path, "r") as file_handle:
                    raw = file_handle.read()

                payload = json.loads(raw)
                validation = self.validate_payload(payload, file_type, strict=True, thorough=True)
                if not validation.valid:
                    logger.error("Validation failed for %s: %s", file_path, validation.to_dict())
                    continue

                transformed = self.transform_payload(payload, file_type)
                if thing_id:
                    transformed.setdefault("attributes", {})["thingId"] = thing_id
                things[file_path] = transformed
                logger.info("Processed %s as %s", file_path, file_type)
            except Exception as exc:
                logger.error("Failed to process %s: %s", file_path, exc)

        self._add_cross_references(things)
        return things

    def _add_cross_references(self, things):
        logger = logging.getLogger(__name__)

        cyclonedx_things = {key: value for key, value in things.items() if value["attributes"].get("sourceType") == "cyclonedx"}
        for thing_id, thing in things.items():
            cross_refs = []

            if thing["attributes"].get("sourceType") == "oscal-component":
                for cyclone_id in cyclonedx_things.keys():
                    cross_refs.append(
                        {"target": cyclone_id, "relationship": "governs", "type": "compliance"}
                    )

            if thing["attributes"].get("sourceType") == "arm-template":
                for cyclone_id in cyclonedx_things.keys():
                    cross_refs.append(
                        {"target": cyclone_id, "relationship": "deploys", "type": "deployment"}
                    )

            if cross_refs:
                thing["_cross_references"] = cross_refs
                logger.info("Added %s cross-references to %s", len(cross_refs), thing_id)

    def detect_bom_type(self, cyclone_content):
        if "components" in cyclone_content:
            components = cyclone_content.get("components", [])
            for component in components:
                if component.get("type") == "cryptographic-asset":
                    if component.get("cryptoProperties", {}).get("assetType") == "algorithm":
                        name = "cbom.algorithm"
                        return name + ".dependencies" if "dependencies" in cyclone_content else name
                    if component.get("cryptoProperties", {}).get("assetType") == "certificate":
                        name = "cbom.certificate"
                        return name + ".dependencies" if "dependencies" in cyclone_content else name
                elif component.get("type") == "library":
                    return "sbom"
                elif component.get("type") == "device":
                    return "hbom"
        elif "dependencies" in cyclone_content and "services" in cyclone_content:
            return "saasbom"
        elif "vulnerabilities" in cyclone_content:
            return "vex"
        return "boms"

    def _coerce_payload_to_dict(self, payload: Any) -> Optional[Dict[str, Any]]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                loaded = json.loads(payload)
                return loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _coerce_payload_to_json(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)

    def _validate_with_jsonschema(self, payload: Dict[str, Any], schema: Dict[str, Any]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        if Draft202012Validator is None:
            return issues

        validator = Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(payload), key=lambda error: list(error.path)):
            path = "$." + ".".join([str(part) for part in err.path]) if err.path else "$"
            issues.append(
                ValidationIssue(
                    path=path,
                    message=err.message,
                    rule="jsonschema",
                )
            )
        return issues

    def _jsonschema_warnings(self) -> List[str]:
        if Draft202012Validator is None:
            return [
                "jsonschema is not installed; schema checks were limited to structural and semantic checks"
            ]
        return []

    def _get_builtin_schema(self, fmt: str) -> Dict[str, Any]:
        if fmt in self._schema_cache:
            return self._schema_cache[fmt]

        if fmt == "oscal":
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["component-definition"],
                "properties": {
                    "component-definition": {
                        "type": "object",
                        "required": ["metadata"],
                        "properties": {
                            "metadata": {"type": "object"},
                            "components": {"type": "array"},
                            "capabilities": {"type": "array"},
                            "back-matter": {"type": "object"},
                        },
                    }
                },
            }
        elif fmt == "arm":
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["$schema", "resources"],
                "properties": {
                    "$schema": {"type": "string"},
                    "contentVersion": {"type": "string"},
                    "parameters": {"type": "object"},
                    "variables": {"type": "object"},
                    "resources": {"type": "array"},
                    "outputs": {"type": "object"},
                },
            }
        elif fmt == "mud":
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["ietf-mud:mud"],
                "properties": {
                    "ietf-mud:mud": {
                        "type": "object",
                        "required": ["mud-version", "mud-url", "last-update"],
                        "properties": {
                            "mud-version": {"type": "integer"},
                            "mud-url": {"type": "string"},
                            "last-update": {"type": "string"},
                            "from-device-policy": {"type": "object"},
                            "to-device-policy": {"type": "object"},
                        },
                    },
                    "ietf-access-control-list:acls": {"type": "object"},
                },
            }
        else:
            schema = {"type": "object"}

        self._schema_cache[fmt] = schema
        return schema
