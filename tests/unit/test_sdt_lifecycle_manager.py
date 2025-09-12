import pytest
from unittest.mock import MagicMock, patch
from sdt_lifecycle_manager import SDT_LifeCycleManager

@pytest.fixture
def lifecycle_manager():
    manager = SDT_LifeCycleManager()
    manager.run_command = MagicMock()
    return manager

def test_deploy_pod(lifecycle_manager):
    lifecycle_manager.run_command.return_value = "sdt-pod-1"
    pod_name, pod_id = lifecycle_manager.deploy_pod()
    assert pod_name == "sdt-pod-1"
    assert pod_id is not None

def test_check_pod_running(lifecycle_manager):
    lifecycle_manager.run_command.return_value = "Running"
    assert lifecycle_manager.check_pod_running() is True

def test_delete_deployment(lifecycle_manager):
    lifecycle_manager.run_command.return_value = "deleted"
    lifecycle_manager.pod_map = {"pod1": "id1"}
    result = lifecycle_manager.delete_deployment_by_id("id1")
    assert result["id1"] is True