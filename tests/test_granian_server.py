import granian

from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import BaseBootstrapSettings


def test_granian_server(base_settings: BaseBootstrapSettings) -> None:
    assert isinstance(create_granian_server("some:app", base_settings), granian.Granian)
