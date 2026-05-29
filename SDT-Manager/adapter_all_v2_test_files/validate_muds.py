import os
import sys
import json
import importlib.util

# Set paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_PATH = os.path.join(BASE_DIR, "adapter_all_v2.py")
TEST_FILES_DIR = os.path.join(BASE_DIR, "adapter_all_v2_test_files")

# Add BASE_DIR to sys.path so adapter_all_v2 can find adapter_all
sys.path.append(BASE_DIR)

# Load adapter_all_v2 module
spec = importlib.util.spec_from_file_location("adapter_all_v2", ADAPTER_PATH)
adapter = importlib.util.module_from_spec(spec)
sys.modules["adapter_all_v2"] = adapter
spec.loader.exec_module(adapter)

json_files = sorted([os.path.join(TEST_FILES_DIR, f) for f in os.listdir(TEST_FILES_DIR) if f.endswith('.json')])

if not json_files:
    print(f"No files found in {TEST_FILES_DIR}")
    sys.exit(0)

print(f"{'File':<30} | {'Valid':<5} | {'Transformed':<11} | {'Err Count':<9} | {'First Error'}")
print("-" * 100)

for file_path in json_files:
    try:
        with open(file_path, 'r') as f:
            payload = json.load(f)
            
        instance = adapter.DTModelAdapterV2()
        validation_result, transformed = instance.validate_and_transform(
            payload,
            'mud',
            strict=True,
            thorough=True,
        )
        
        file_name = os.path.basename(file_path)
        errors = list(validation_result.errors) if validation_result else []
        if errors:
            first_issue = errors[0]
            err_msg = f"{first_issue.path}: {first_issue.message}"
        else:
            err_msg = ""
        print(
            f"{file_name:<30} | {str(validation_result.valid):<5} | "
            f"{str(bool(transformed)):<11} | {len(errors):<9} | {err_msg}"
        )
        
    except Exception as e:
        print(f"{os.path.basename(file_path):<30} | ERROR: {str(e)}")

print("\nExact file paths tested:")
for f in json_files:
    print(f)
