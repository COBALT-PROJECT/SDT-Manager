import pytest
from unittest.mock import MagicMock, patch
from sdt_connector_manager import SDT_ConnectorManager

@pytest.fixture
def connector_manager():
    with patch('sdt_connector_manager.IDS_Connector') as mock_connector:
        manager = SDT_ConnectorManager()
        manager.ids_connector = mock_connector
        return manager

def test_deploy_connector(connector_manager):
    connector_manager.ids_connector.deploy.return_value = ("deploy1", "conn1")
    result = connector_manager.deploy_connector("consumer")
    assert result == ("deploy1", "conn1")

def test_delete_connector(connector_manager):
    connector_manager.ids_connector.delete_connector_by_id.return_value = {"conn1": True}
    result = connector_manager.delete_connector("conn1")
    assert result["conn1"] is True

def test_list_connectors(connector_manager):
    connector_manager.ids_connector.list_available_connectors.return_value = [{"id": "conn1"}]
    result = connector_manager.list_connectors()
    assert len(result) == 1