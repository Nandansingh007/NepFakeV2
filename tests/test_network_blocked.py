"""
Guard test: proves the network block in pytest.ini is actually active.
If someone removes --disable-socket, this test fails.
"""
import socket

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_network_is_blocked_in_tests():
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
