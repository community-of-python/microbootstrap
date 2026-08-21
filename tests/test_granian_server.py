import granian
from granian.constants import Interfaces

from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import ServerConfig


def test_granian_server(minimal_server_config: ServerConfig) -> None:
    server = create_granian_server("some:app", minimal_server_config)

    assert isinstance(server, granian.Granian)
    assert server.interface is Interfaces.ASGI


def test_granian_server_custom_interface(minimal_server_config: ServerConfig) -> None:
    server = create_granian_server("some:app", minimal_server_config, interface=Interfaces.ASGINL)

    assert server.interface is Interfaces.ASGINL
