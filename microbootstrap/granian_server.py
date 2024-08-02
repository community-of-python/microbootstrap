from __future__ import annotations
import logging
import typing

import granian
from granian.constants import Interfaces, Loops
from granian.log import LogLevels


if typing.TYPE_CHECKING:
    from microbootstrap.settings import BaseBootstrapSettings


GRANIAN_LOG_LEVELS_MAP = {
    logging.CRITICAL: LogLevels.critical,
    logging.ERROR: LogLevels.error,
    logging.WARNING: LogLevels.warning,
    logging.WARNING: LogLevels.warn,
    logging.INFO: LogLevels.info,
    logging.DEBUG: LogLevels.debug,
}


# TODO: create bootstrappers for application servers. granian/uvicorn  # noqa: TD002
def create_granian_server(
    target: str,
    settings: BaseBootstrapSettings,
    **granian_options: typing.Any,  # noqa: ANN401
) -> granian.Granian:
    return granian.Granian(
        target=target,
        address=settings.server_host,
        port=settings.server_port,
        interface=Interfaces.ASGI,
        loop=Loops.uvloop,
        workers=settings.server_workers_count,
        log_level=GRANIAN_LOG_LEVELS_MAP[settings.logging_log_level],
        reload=settings.server_reload,
        **granian_options,
    )