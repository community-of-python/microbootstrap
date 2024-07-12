from __future__ import annotations
import abc
import dataclasses
import logging
import logging.handlers
import typing
import warnings

import structlog
from opentelemetry import trace

from microbootstrap.base.base import BootstrapServicesBootstrapper, Settings_contra


if typing.TYPE_CHECKING:
    from structlog.typing import EventDict, WrappedLogger


BASE_LOG_LEVEL: typing.Final = logging.INFO
BASE_FLUSH_LEVEL: typing.Final = logging.ERROR
BASE_CAPACITY: typing.Final = 0


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


@dataclasses.dataclass()
class BaseLoggingBootstrapper(abc.ABC, BootstrapServicesBootstrapper[Settings_contra]):
    log_level: int = dataclasses.field(default=BASE_LOG_LEVEL)
    flush_level: int = dataclasses.field(default=BASE_FLUSH_LEVEL)
    buffer_capacity: int = dataclasses.field(default=BASE_CAPACITY)
    is_debug: bool = dataclasses.field(default=True)
    extra_processors: list[typing.Any] = dataclasses.field(default_factory=list)

    def load_parameters(self, settings: Settings_contra | None = None) -> None:
        if not settings:
            return

        self.log_level = settings.logging_log_level
        self.flush_level = settings.logging_flush_level
        self.buffer_capacity = settings.logging_buffer_capacity
        self.is_debug = settings.debug
        self.extra_processors = settings.logging_extra_processors

    def initialize(self) -> None:
        if not self.ready:
            return

        if self.buffer_capacity == BASE_CAPACITY:
            warnings.warn(
                "Your buffer capacity is 0 in non-debug mode. "
                "Please provide a valid buffer size, to get buffer usage time-advantage. "
                "Default value can be 1024*100, highly recommended to figure out value based on current sitiation.",
                stacklevel=2,
            )

        root_logger = logging.getLogger()
        stream_handler = logging.StreamHandler()  # Creates a new stream handler
        stream_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer()),
        )
        handler = logging.handlers.MemoryHandler(
            capacity=self.buffer_capacity,
            flushLevel=self.flush_level,
            target=stream_handler,  # Set the target of MemoryHandler to the stream handler
        )
        root_logger.addHandler(handler)
        root_logger.setLevel(self.log_level)

        # Unset default uvicorn loggers
        logging.getLogger("uvicorn.access").handlers = []
        logging.getLogger("uvicorn").handlers = []

    def teardown(self) -> None:
        root_logger = logging.getLogger()

        for logger_handler in root_logger.handlers:
            root_logger.removeHandler(logger_handler)
        for logger_filter in root_logger.filters:
            root_logger.removeFilter(logger_filter)

        structlog.reset_defaults()

    @property
    def ready(self) -> bool:
        return not self.is_debug


@dataclasses.dataclass()
class LoggingBootstrapper(BaseLoggingBootstrapper[Settings_contra]):
    def initialize(self) -> None:
        super().initialize()

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
