from __future__ import annotations
import time
import typing
import urllib.parse

import structlog


if typing.TYPE_CHECKING:
    import fastapi
    import litestar

    from microbootstrap.middlewares.logging_level import LogLevel


ACCESS_LOGGER: typing.Final = structlog.get_logger("api.access")

ScopeType = typing.MutableMapping[str, typing.Any]


def make_path_with_query_string(scope: ScopeType) -> str:
    path_with_query_string: typing.Final = urllib.parse.quote(scope["path"])
    if scope["query_string"]:
        return f'{path_with_query_string}?{scope["query_string"].decode("ascii")}'
    return path_with_query_string


def fill_log_message(
    log_level: LogLevel,
    request: litestar.Request[typing.Any, typing.Any, typing.Any] | fastapi.Request,
    status_code: int,
    start_time: int,
) -> None:
    process_time: typing.Final = time.perf_counter_ns() - start_time
    url_with_query: typing.Final = make_path_with_query_string(typing.cast(ScopeType, request.scope))
    client_host: typing.Final = request.client.host if request.client is not None else None
    client_port: typing.Final = request.client.port if request.client is not None else None
    http_method: typing.Final = request.method
    http_version: typing.Final = request.scope["http_version"]
    log_on_correct_level: typing.Final = getattr(typing.cast(typing.Any, ACCESS_LOGGER), log_level)
    log_on_correct_level(
        f"""{client_host}:{client_port} - "{http_method} {url_with_query} HTTP/{http_version}" {status_code}""",
        http={
            "url": str(request.url),
            "status_code": status_code,
            "method": http_method,
            "version": http_version,
        },
        network={"client": {"ip": client_host, "port": client_port}},
        duration=process_time,
    )
