import pytest
from unittest.mock import MagicMock, patch
from sdt_manager_core import SDT_ManagerCore

@pytest.fixture
def manager_core(mock_logger, mock_os_environ):
    with patch('sdt_manager_core.SDT_LifeCycleManager'), \
         patch('sdt_manager_core.SDT_ConnectorManager'), \
         patch('sdt_manager_core.DTModelAdapter'), \
         patch('sdt_manager_core.CCM_Manager_Interface'):
        return SDT_ManagerCore()

def test_sdt_manager_core_init(manager_core):
    assert manager_core is not None
    assert hasattr(manager_core, 'lifecycle_manager')
    assert hasattr(manager_core, 'connector_manager')
    assert hasattr(manager_core, 'sdt_adapter')
    assert hasattr(manager_core, 'ccm_manager')

def test_sdt_manager_core_start(manager_core):
    with patch.object(manager_core.ccm_manager, 'start_server_thread') as mock_start:
        manager_core.start()
        mock_start.assert_called_once_with(
            host='0.0.0.0',
            port=8008
        )

def test_sdt_manager_core_stop(manager_core):
    manager_core.start()
    manager_core.stop()
    assert manager_core.terminate_event.is_set()