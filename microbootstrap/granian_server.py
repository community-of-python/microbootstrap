from __future__ import annotations
import typing

import granian
from granian.constants import Interfaces, Loops
from granian.log import log_levels_map


if typing.TYPE_CHECKING:
    from microbootstrap.settings import BootstrapSettings


# TODO: create bootstrappers for application servers. granian/uvicorn  # noqa: TD002
def create_granian_server(
    target: str,
    settings: BootstrapSettings,
    **granian_options: typing.Any,  # noqa: ANN401
) -> granian.Granian:
    return granian.Granian(
        target=target,
        address=settings.server_host,
        port=settings.server_port,
        interface=Interfaces.ASGI,
        loop=Loops.uvloop,
        workers=settings.server_workers_count,
        log_level=log_levels_map[settings.logging_log_level],
        reload=settings.server_reload,
        **granian_options,
    )
