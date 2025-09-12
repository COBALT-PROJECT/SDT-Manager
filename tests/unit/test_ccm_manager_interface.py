import pytest
from fastapi.testclient import TestClient
from ccm_manager_interface import CCM_Manager_Interface
from unittest.mock import MagicMock

@pytest.fixture
def mock_manager_core():
    core = MagicMock()
    core.sdt_adapter = MagicMock()
    core.sdt_adapter.validate_cyclonedx_smart.return_value = True
    core.sdt_adapter.from_cyclone.return_value = {"converted": "data"}
    core.sdt_adapter.send_to_controller.return_value = MagicMock(status_code=200, text='success')
    return core

@pytest.fixture
def client(mock_manager_core):
    ccm = CCM_Manager_Interface(mock_manager_core)
    return TestClient(ccm.app)

def test_create_sdt_endpoint(client):
    response = client.post(
        "/api/SDT/create/?toeid=123&payload_type=BOMS",
        json={"bomFormat": "CycloneDX"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_deploy_sdt_endpoint(client, mock_manager_core):
    mock_manager_core.lifecycle_manager.deploy.return_value = ("pod1", "id1")
    response = client.post("/deploy")
    assert response.status_code == 200
    assert response.json()["pod_name"] == "pod1"

def test_list_connectors_endpoint(client, mock_manager_core):
    mock_manager_core.connector_manager.list_connectors.return_value = []
    response = client.get("/connectors")
    assert response.status_code == 200
    assert response.json() == {"connectors": []}