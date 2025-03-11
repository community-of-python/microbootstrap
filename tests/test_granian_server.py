import granian

from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import ServerConfig


def test_granian_server(minimal_server_config: ServerConfig) -> None:
    assert isinstance(create_granian_server("some:app", minimal_server_config), granian.Granian)  # type: ignore[attr-defined]
