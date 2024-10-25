import granian

from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import BaseServerSettings


def test_granian_server(base_server_settings: BaseServerSettings) -> None:
    assert isinstance(create_granian_server("some:app", base_server_settings), granian.Granian)
