from __future__ import annotations
import logging
import time
import typing
import urllib.parse

import pydantic
import structlog
from opentelemetry import trace

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


if typing.TYPE_CHECKING:
    import fastapi
    import litestar
    from structlog.typing import EventDict, WrappedLogger


BASE_LOG_LEVEL: typing.Final = logging.INFO
BASE_FLUSH_LEVEL: typing.Final = logging.ERROR
BASE_CAPACITY: typing.Final = 100


ACCESS_LOGGER: typing.Final = structlog.get_logger("api.access")

ScopeType = typing.MutableMapping[str, typing.Any]


def make_path_with_query_string(scope: ScopeType) -> str:
    path_with_query_string: typing.Final = urllib.parse.quote(scope["path"])
    if scope["query_string"]:
        return f'{path_with_query_string}?{scope["query_string"].decode("ascii")}'
    return path_with_query_string


def fill_log_message(
    log_level: str,
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


def tracer_injection(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["tracing"] = {}

    def inject_invalid_trace_span_id() -> EventDict:
        event_dict["tracing"]["trace_id"] = event_dict["tracing"]["span_id"] = "0"
        return event_dict

    current_span: typing.Final[trace.Span] = trace.get_current_span()
    if current_span == trace.INVALID_SPAN:
        return inject_invalid_trace_span_id()

    span_context: typing.Final[trace.SpanContext] = current_span.get_span_context()
    if span_context == trace.INVALID_SPAN_CONTEXT:
        return inject_invalid_trace_span_id()

    event_dict["tracing"]["trace_id"] = format(span_context.span_id, "016x")
    event_dict["tracing"]["span_id"] = format(span_context.trace_id, "032x")

    return event_dict


DEFAULT_STRUCTLOG_PROCESSORS: typing.Final[list[typing.Any]] = [
    structlog.stdlib.filter_by_level,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    tracer_injection,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]
DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR: typing.Final[typing.Any] = structlog.stdlib.ProcessorFormatter.wrap_for_formatter


class LoggingConfig(BaseInstrumentConfig):
    debug: bool = False

    logging_log_level: int = BASE_LOG_LEVEL
    logging_flush_level: int = BASE_FLUSH_LEVEL
    logging_buffer_capacity: int = BASE_CAPACITY
    logging_extra_processors: list[typing.Any] = pydantic.Field(default_factory=list)
    logging_unset_handlers: list[str] = pydantic.Field(default_factory=lambda: ["uvicorn", "uvicorn.access"])
    logging_exclude_endpoings: list[str] = pydantic.Field(default_factory=lambda: ["/health"])


class LoggingInstrument(Instrument[LoggingConfig]):
    @property
    def is_ready(self) -> bool:
        return self.instrument_config.debug

    def teardown(self) -> None:
        root_logger: typing.Final = logging.getLogger()

        for logger_handler in root_logger.handlers:
            root_logger.removeHandler(logger_handler)
        for logger_filter in root_logger.filters:
            root_logger.removeFilter(logger_filter)

        structlog.reset_defaults()

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready:
            print("Skipping logging bootstrap.")  # noqa: T201
            return {}

        root_logger: typing.Final = logging.getLogger()
        stream_handler: typing.Final = logging.StreamHandler()
        stream_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer()),
        )
        handler: typing.Final = logging.handlers.MemoryHandler(
            capacity=self.buffer_capacity,
            flushLevel=self.flush_level,
            target=stream_handler,
        )
        root_logger.addHandler(handler)
        root_logger.setLevel(self.log_level)

        for unset_handlers_logger in self.instrument_config.logging_unset_handlers:
            logging.getLogger(unset_handlers_logger).handlers = []

        structlog.configure(
            processors=[
                *DEFAULT_STRUCTLOG_PROCESSORS,
                *self.extra_processors,
                DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR,
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        return self.successful_bootstrap_result
