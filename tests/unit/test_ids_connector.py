import pytest
from unittest.mock import MagicMock, patch
from ids_connector import IDS_Connector

@pytest.fixture
def ids_connector():
    connector = IDS_Connector()
    connector.run_command = MagicMock()
    return connector

def test_deploy_connector(ids_connector):
    ids_connector.run_command.return_value = "deployment-1"
    deploy_name, conn_id = ids_connector.deploy_connector("consumer")
    assert deploy_name == "deployment-1"
    assert conn_id is not None

def test_delete_connector(ids_connector):
    ids_connector.deployment_map = {"deploy1": "conn1"}
    ids_connector.run_command.return_value = "deleted"
    result = ids_connector.delete_connector_by_id("conn1")
    assert result["conn1"] is True

def test_list_available_connectors(ids_connector):
    ids_connector.deployment_map = {"deploy1": "conn1"}
    result = ids_connector.list_available_connectors()
    assert len(result) == 1
    assert result[0]["connector_id"] == "conn1"