from __future__ import annotations
import logging
import logging.handlers
import time
import typing
import urllib.parse

import orjson
import pydantic
import structlog
import typing_extensions
from opentelemetry import trace

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


if typing.TYPE_CHECKING:
    import fastapi
    import litestar
    from structlog.typing import EventDict, WrappedLogger


ScopeType = typing.MutableMapping[str, typing.Any]

access_logger: typing.Final = structlog.get_logger("api.access")


def make_path_with_query_string(scope: ScopeType) -> str:
    path_with_query_string: typing.Final = urllib.parse.quote(scope["path"])
    if scope["query_string"]:
        return f"{path_with_query_string}?{scope['query_string'].decode('ascii')}"
    return path_with_query_string


def fill_log_message(
    log_level: str,
    request: litestar.Request[typing.Any, typing.Any, typing.Any] | fastapi.Request,
    status_code: int,
    start_time: int,
) -> None:
    process_time: typing.Final = time.perf_counter_ns() - start_time
    url_with_query: typing.Final = make_path_with_query_string(typing.cast("ScopeType", request.scope))
    client_host: typing.Final = request.client.host if request.client is not None else None
    client_port: typing.Final = request.client.port if request.client is not None else None
    http_method: typing.Final = request.method
    http_version: typing.Final = request.scope["http_version"]
    log_on_correct_level: typing.Final = getattr(access_logger, log_level)
    log_on_correct_level(
        http={
            "url": url_with_query,
            "status_code": status_code,
            "method": http_method,
            "version": http_version,
        },
        network={"client": {"ip": client_host, "port": client_port}},
        duration=process_time,
    )


def tracer_injection(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    current_span = trace.get_current_span()
    if not current_span.is_recording():
        event_dict["tracing"] = {}
        return event_dict

    current_span_context = current_span.get_span_context()
    event_dict["tracing"] = {
        "span_id": trace.format_span_id(current_span_context.span_id),
        "trace_id": trace.format_trace_id(current_span_context.trace_id),
    }
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
DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR: typing.Final = structlog.processors.JSONRenderer(serializer=orjson.dumps)


class MemoryLoggerFactory(structlog.stdlib.LoggerFactory):
    def __init__(
        self,
        *args: typing.Any,  # noqa: ANN401
        logging_buffer_capacity: int,
        logging_flush_level: int,
        logging_log_level: int,
        log_stream: typing.Any = None,  # noqa: ANN401
        **kwargs: typing.Any,  # noqa: ANN401
    ) -> None:
        super().__init__(*args, **kwargs)
        self.logging_buffer_capacity = logging_buffer_capacity
        self.logging_flush_level = logging_flush_level
        self.logging_log_level = logging_log_level
        self.log_stream = log_stream

    def __call__(self, *args: typing.Any) -> logging.Logger:  # noqa: ANN401
        logger: typing.Final = super().__call__(*args)
        stream_handler: typing.Final = logging.StreamHandler(stream=self.log_stream)
        handler: typing.Final = logging.handlers.MemoryHandler(
            capacity=self.logging_buffer_capacity,
            flushLevel=self.logging_flush_level,
            target=stream_handler,
        )
        logger.addHandler(handler)
        logger.setLevel(self.logging_log_level)
        logger.propagate = False
        return logger


class LoggingConfig(BaseInstrumentConfig):
    service_debug: bool = True

    logging_log_level: int = logging.INFO
    logging_flush_level: int = logging.ERROR
    logging_buffer_capacity: int = 10
    logging_extra_processors: list[typing.Any] = pydantic.Field(default_factory=list)
    logging_unset_handlers: list[str] = pydantic.Field(
        default_factory=lambda: ["uvicorn", "uvicorn.access"],
    )
    logging_exclude_endpoints: list[str] = pydantic.Field(default_factory=lambda: ["/health/", "/metrics"])
    logging_turn_off_middleware: bool = False

    @pydantic.model_validator(mode="after")
    def remove_trailing_slashes_from_logging_exclude_endpoints(self) -> typing_extensions.Self:
        self.logging_exclude_endpoints = [
            one_endpoint.removesuffix("/") for one_endpoint in self.logging_exclude_endpoints
        ]
        return self


class LoggingInstrument(Instrument[LoggingConfig]):
    instrument_name = "Logging"
    ready_condition = "Works only in non-debug mode"

    def is_ready(self) -> bool:
        return not self.instrument_config.service_debug

    def teardown(self) -> None:
        structlog.reset_defaults()

    def bootstrap(self) -> None:
        for unset_handlers_logger in self.instrument_config.logging_unset_handlers:
            logging.getLogger(unset_handlers_logger).handlers = []

        structlog.configure(
            processors=[
                *DEFAULT_STRUCTLOG_PROCESSORS,
                *self.instrument_config.logging_extra_processors,
                DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR,
            ],
            context_class=dict,
            logger_factory=MemoryLoggerFactory(
                logging_buffer_capacity=self.instrument_config.logging_buffer_capacity,
                logging_flush_level=self.instrument_config.logging_flush_level,
                logging_log_level=self.instrument_config.logging_log_level,
            ),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    @classmethod
    def get_config_type(cls) -> type[LoggingConfig]:
        return LoggingConfig
