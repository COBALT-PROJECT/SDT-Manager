import sys
import os
import json
import inspect
import shutil
import subprocess
import re

# Resolve paths relative to this script so it works from any current directory.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, ADAPTER_DIR)

try:
    from adapter_all_v2 import DTModelAdapterV2
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

adapter = DTModelAdapterV2()

print(f"Signature: {inspect.signature(adapter.validate_and_transform)}")


def run_official_mud_tooling_check():
    """
    Attempt an official-model tooling check using pyang, if available.

    Note: pyang validates YANG model syntax/consistency. It does not directly
    validate each JSON instance payload by itself in this script.
    """
    print("Official MUD/YANG tooling check:")

    pyang_bin = shutil.which("pyang")
    if not pyang_bin:
        print("- SKIP: pyang is not installed in this environment")
        return

    # You can pass the IETF MUD YANG module path via env, for example:
    # export MUD_YANG_MODULE=/path/to/ietf-mud.yang
    yang_module = os.environ.get("MUD_YANG_MODULE")
    if not yang_module:
        print("- SKIP: MUD_YANG_MODULE is not set")
        return

    if not os.path.exists(yang_module):
        print(f"- SKIP: MUD_YANG_MODULE file not found: {yang_module}")
        return

    try:
        completed = subprocess.run(
            [pyang_bin, yang_module],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            print(f"- PASS: pyang validated module syntax: {yang_module}")
        else:
            print(f"- FAIL: pyang reported issues for module: {yang_module}")
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            if stderr:
                print(f"  pyang stderr: {stderr}")
            elif stdout:
                print(f"  pyang output: {stdout}")
    except Exception as exc:
        print(f"- ERROR: Failed to execute pyang: {exc}")


run_official_mud_tooling_check()


def _parse_module_metadata(yang_file_path):
    """Extract module name, revision, and namespace from a .yang module file."""
    module_name = None
    revision = None
    namespace = None

    try:
        with open(yang_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if module_name is None:
                    m = re.match(r"^\s*module\s+([A-Za-z0-9._-]+)\s*\{", line)
                    if m:
                        module_name = m.group(1)

                if namespace is None:
                    m = re.match(r"^\s*namespace\s+\"([^\"]+)\"\s*;", line)
                    if m:
                        namespace = m.group(1)

                if revision is None:
                    m = re.match(r"^\s*revision\s+\"?([0-9]{4}-[0-9]{2}-[0-9]{2})\"?\s*\{?", line)
                    if m:
                        revision = m.group(1)

                if module_name and namespace and revision:
                    break
    except Exception:
        return None

    # Skip submodules or incomplete module metadata.
    if not module_name or not namespace or not revision:
        return None

    return {
        "name": module_name,
        "revision": revision,
        "namespace": namespace,
    }


def build_local_yang_library_and_model():
    """
    Build a Yangson DataModel from locally installed YANG modules.

    Uses MUD_YANG_MODULE as anchor and scans nearby module directories.
    Optionally extends search paths with MUD_EXTENSION_YANG_DIRS (':' separated).
    By default, SCRIPT_DIR is included as an extension module directory.
    """
    try:
        from yangson.datamodel import DataModel
    except Exception as exc:
        print(f"- SKIP: yangson is not available ({exc})")
        return None

    mud_yang_module = os.environ.get("MUD_YANG_MODULE")
    if not mud_yang_module:
        print("- SKIP: MUD_YANG_MODULE is not set (cannot build Yangson model)")
        return None

    if not os.path.exists(mud_yang_module):
        print(f"- SKIP: MUD_YANG_MODULE file not found: {mud_yang_module}")
        return None

    ietf_dir = os.path.dirname(mud_yang_module)
    modules_root = os.path.dirname(ietf_dir)
    iana_dir = os.path.join(modules_root, "iana")

    module_dirs = [ietf_dir]
    if os.path.isdir(iana_dir):
        module_dirs.append(iana_dir)

    extension_dirs = [SCRIPT_DIR]
    extension_dirs_env = os.environ.get("MUD_EXTENSION_YANG_DIRS", "").strip()
    if extension_dirs_env:
        extension_dirs.extend([d for d in extension_dirs_env.split(":") if d])

    for ext_dir in extension_dirs:
        if os.path.isdir(ext_dir) and ext_dir not in module_dirs:
            module_dirs.append(ext_dir)

    module_entries = []
    seen_modules = set()
    for module_dir in module_dirs:
        for filename in os.listdir(module_dir):
            if not filename.endswith(".yang"):
                continue
            full_path = os.path.join(module_dir, filename)
            meta = _parse_module_metadata(full_path)
            if not meta:
                continue
            module_key = (meta["name"], meta["revision"])
            if module_key in seen_modules:
                continue
            seen_modules.add(module_key)
            entry = {
                "name": meta["name"],
                "revision": meta["revision"],
                "namespace": meta["namespace"],
                "conformance-type": "implement",
            }
            module_entries.append(entry)

    if not module_entries:
        print("- SKIP: No suitable YANG module entries found for Yangson")
        return None

    yang_library = {
        "ietf-yang-library:modules-state": {
            "module-set-id": "local-mud-test-set",
            "module": module_entries,
        }
    }

    try:
        model = DataModel(json.dumps(yang_library), mod_path=module_dirs)
        print(
            f"- PASS: Yangson DataModel built with {len(module_entries)} modules "
            f"from {', '.join(module_dirs)}"
        )
        return model
    except Exception as exc:
        print(f"- FAIL: Could not build Yangson DataModel ({exc})")
        return None


print("Official MUD instance validation (YANG data-model):")
yangson_model = build_local_yang_library_and_model()

print("Adapter validation results:")

test_files = [
    os.path.join(SCRIPT_DIR, "example_MUD_1.json"),
    os.path.join(SCRIPT_DIR, "example_MUD_2.json"),
    os.path.join(SCRIPT_DIR, "example_extended_MUD_1.json"),
]

for file_path in test_files:
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        continue
    
    with open(file_path, 'r') as f:
        try:
            payload = json.load(f)
        except Exception as e:
            print(f"JSON Load error for {file_path}: {e}")
            continue

    # Run official-style instance validation against YANG model if available.
    if yangson_model is not None:
        try:
            from yangson.enumerations import ValidationScope, ContentType

            root = yangson_model.from_raw(payload)
            root.validate(scope=ValidationScope.all, ctype=ContentType.all)
            yangson_status = "PASS"
            yangson_error = None
        except Exception as exc:
            yangson_status = "FAIL"
            yangson_error = str(exc)
    else:
        yangson_status = "SKIP"
        yangson_error = "Yangson model unavailable"

    try:
        result = adapter.validate_and_transform(payload, 'mud', strict=True, thorough=True)

        # Handle adapter return shapes and extract ValidationResult correctly.
        validation_result = None
        transformed_payload = None
        fallback_errors = []

        if isinstance(result, tuple):
            if len(result) == 2:
                validation_result, transformed_payload = result
            elif len(result) == 3:
                validation_result, transformed_payload, fallback_errors = result
            else:
                fallback_errors = [f"Unexpected return tuple length: {len(result)}"]
        else:
            fallback_errors = ["Unexpected return type"]

        if hasattr(validation_result, "valid"):
            is_valid = bool(validation_result.valid)
            validation_errors = list(getattr(validation_result, "errors", []) or [])
            error_count = len(validation_errors)
            if error_count > 0:
                first_issue = validation_errors[0]
                first_error = f"{getattr(first_issue, 'path', '$')}: {getattr(first_issue, 'message', first_issue)}"
            else:
                first_error = None
        else:
            is_valid = False
            error_count = len(fallback_errors) if isinstance(fallback_errors, list) else (1 if fallback_errors else 0)
            first_error = fallback_errors[0] if error_count > 0 and isinstance(fallback_errors, list) else fallback_errors

        has_transformed = transformed_payload is not None

        print(f"File: {os.path.basename(file_path)}")
        print(f"Official Instance Validation: {yangson_status}")
        if yangson_error and yangson_status != "PASS":
            print(f"Official Validation Detail: {yangson_error}")
        print(f"Valid: {is_valid}")
        print(f"Transformed: {has_transformed}")
        print(f"Error Count: {error_count}")
        if error_count > 0:
            print(f"First Error: {first_error}")
        print("-" * 20)

    except Exception as e:
        print(f"Execution error for {file_path}: {e}")
        import traceback
        traceback.print_exc()
