import granian

from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import ServerConfig


def test_granian_server(base_server_settings: ServerConfig) -> None:
    assert isinstance(create_granian_server("some:app", base_server_settings), granian.Granian)
