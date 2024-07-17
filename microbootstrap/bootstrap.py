from __future__ import annotations
import typing


if typing.TYPE_CHECKING:
    import granian

    from microbootstrap.settings.base import BootstrapSettings


def create_granian_server(
    target: str,
    settings: BootstrapSettings,
    **granian_options: typing.Any,  # noqa: ANN401
) -> granian.Granian:
    import granian
    from granian.constants import Interfaces, Loops
    from granian.log import log_levels_map

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
