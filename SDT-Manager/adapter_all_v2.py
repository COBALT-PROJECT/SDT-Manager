import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from adapter_all import DTModelAdapter

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - optional dependency fallback
    Draft202012Validator = None


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
                {"path": i.path, "message": i.message, "rule": i.rule}
                for i in self.errors
            ],
            "warnings": self.warnings,
        }


@dataclass
class FormatSpec:
    canonical: str
    validator: Callable[..., ValidationResult]
    transformer: Callable[..., Dict[str, Any]]
    schema_version: str


class DTModelAdapterV2(DTModelAdapter):
    """
    V2 adapter with unified validation and transform dispatch for all payload formats.

    This class is backward-compatible with existing adapter usage because it extends
    DTModelAdapter and preserves inherited methods.
    """

    def __init__(self):
        super().__init__()
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

    def from_mud_profile(self, mud_json: str, thing_id: Optional[str] = None) -> Dict[str, Any]:
        """Transform an RFC8520 MUD profile into Thing-like structure."""
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
        """
        V2 batch processing with per-file validation.
        Returns the same things dictionary shape used by existing routes.
        """
        logger = logging.getLogger(__name__)
        things = {}

        for config in file_configs:
            file_path = config["path"]
            file_type = self._normalize_payload_type(config["type"])
            thing_id = config.get("thing_id")

            try:
                with open(file_path, "r") as f:
                    raw = f.read()

                payload = json.loads(raw)
                validation = self.validate_payload(payload, file_type, strict=True, thorough=True)
                if not validation.valid:
                    logger.error(
                        "Validation failed for %s: %s",
                        file_path,
                        validation.to_dict(),
                    )
                    continue

                transformed = self.transform_payload(payload, file_type)
                if thing_id:
                    transformed.setdefault("attributes", {})["thingId"] = thing_id
                things[file_path] = transformed
                logger.info("Processed %s as %s", file_path, file_type)

            except Exception as e:
                logger.error("Failed to process %s: %s", file_path, str(e))

        self._add_cross_references(things)
        return things

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
        for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
            path = "$." + ".".join([str(p) for p in err.path]) if err.path else "$"
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
