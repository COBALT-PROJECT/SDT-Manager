import pytest
from unittest.mock import MagicMock
import logging

@pytest.fixture
def mock_logger(mocker):
    return mocker.patch('logging.getLogger', return_value=MagicMock())

@pytest.fixture
def mock_os_environ(mocker):
    return mocker.patch.dict('os.environ', {
        'SDT_INTERFACE_HOST': 'localhost',
        'SDT_INTERFACE_PORT': '30008',
        'API_SERVER_HOST': '0.0.0.0',
        'API_SERVER_PORT': '8008'
    })