import pytest
from unittest.mock import MagicMock, patch
from adapter import DTModelAdapter
import json

@pytest.fixture
def adapter():
    # Patch the logger to prevent actual logging during tests
    with patch('adapter.logging.getLogger', return_value=MagicMock()):
        return DTModelAdapter()

def test_adapter_init(adapter):
    assert adapter.host == 'localhost'
    assert adapter.port == '30008'

def test_send_to_controller_success(adapter, requests_mock):
    test_url = "http://localhost:30008/api/SDT/create/?toeid=123456789&payload_type=BOMS"
    requests_mock.post(test_url, text='success', status_code=200)
    
    payload = {"test": "data"}
    response = adapter.send_to_controller(payload)
    
    assert response is not None
    assert response.status_code == 200

def test_validate_cyclonedx_smart_valid(adapter):
    valid_payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "serialNumber": "urn:uuid:3e671687-395b-41f5-a30f-a58921a69b79",
        "version": 1,
        "metadata": {
            "timestamp": "2023-01-15T08:30:00Z",
            "tools": [{
                "vendor": "Test",
                "name": "TestTool",
                "version": "1.0"
            }],
            "component": {
                "type": "application",
                "name": "test-app",
                "version": "1.0.0"
            }
        }
    }
    assert adapter.validate_cyclonedx_smart(valid_payload) is True

def test_from_cyclone_conversion(adapter):
    cyclone_json = json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "serialNumber": "urn:uuid:test",
        "metadata": {"test": "data"},
        "components": [{"type": "library"}]
    })
    
    result = adapter.from_cyclone(cyclone_json)
    assert 'attributes' in result
    assert 'features' in result
    assert 'components' in result['features']