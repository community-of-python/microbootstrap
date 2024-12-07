import logging
import typing
from io import StringIO

import fastapi
import litestar
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.testing import TestClient as LitestarTestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from microbootstrap import LoggingConfig
from microbootstrap.bootstrappers.fastapi import FastApiLoggingInstrument
from microbootstrap.bootstrappers.litestar import LitestarLoggingInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument, MemoryLoggerFactory


def test_logging_is_ready(minimal_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimal_logging_config)
    assert logging_instrument.is_ready()


def test_logging_bootstrap_is_not_ready(minimal_logging_config: LoggingConfig) -> None:
    minimal_logging_config.service_debug = True
    logging_instrument: typing.Final = LoggingInstrument(minimal_logging_config)
    assert logging_instrument.bootstrap_before() == {}


def test_logging_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_logging_config: LoggingConfig,
) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimal_logging_config)
    assert logging_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_logging_teardown(
    minimal_logging_config: LoggingConfig,
) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimal_logging_config)
    assert logging_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_logging_bootstrap(minimal_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimal_logging_config)
    logging_instrument.bootstrap()
    bootsrap_result: typing.Final = logging_instrument.bootstrap_before()
    assert "middleware" in bootsrap_result
    assert isinstance(bootsrap_result["middleware"], list)
    assert len(bootsrap_result["middleware"]) == 1


def test_litestar_logging_bootstrap_working(minimal_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimal_logging_config)

    @litestar.get("/test-handler")
    async def error_handler() -> str:
        return "Ok"

    logging_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[error_handler],
        **logging_instrument.bootstrap_before(),
    )

    with LitestarTestClient(app=litestar_application) as test_client:
        test_client.get("/test-handler?test-query=1")
        test_client.get("/test-handler")


def test_litestar_logging_bootstrap_tracer_injection(minimal_logging_config: LoggingConfig) -> None:
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    trace.get_tracer_provider().add_span_processor(span_processor)  # type: ignore[attr-defined]
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimal_logging_config)

    @litestar.get("/test-handler")
    async def test_handler() -> str:
        return "Ok"

    logging_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[test_handler],
        **logging_instrument.bootstrap_before(),
    )
    with tracer.start_as_current_span("my_fake_span") as span:
        # Do some fake work inside the span
        span.set_attribute("example_attribute", "value")
        span.add_event("example_event", {"event_attr": 1})
        with LitestarTestClient(app=litestar_application) as test_client:
            test_client.get("/test-handler")


def test_memory_logger_factory_info() -> None:
    test_capacity: typing.Final = 10
    test_flush_level: typing.Final = logging.ERROR
    test_stream: typing.Final = StringIO()

    logger_factory: typing.Final = MemoryLoggerFactory(
        logging_buffer_capacity=test_capacity,
        logging_flush_level=test_flush_level,
        logging_log_level=logging.INFO,
        log_stream=test_stream,
    )
    test_logger: typing.Final = logger_factory()
    test_message: typing.Final = "test message"

    for current_log_index in range(test_capacity):
        test_logger.info(test_message)
        log_contents = test_stream.getvalue()
        if current_log_index == test_capacity - 1:
            assert test_message in log_contents
        else:
            assert not log_contents


def test_memory_logger_factory_error() -> None:
    test_capacity: typing.Final = 10
    test_flush_level: typing.Final = logging.ERROR
    test_stream: typing.Final = StringIO()

    logger_factory: typing.Final = MemoryLoggerFactory(
        logging_buffer_capacity=test_capacity,
        logging_flush_level=test_flush_level,
        logging_log_level=logging.INFO,
        log_stream=test_stream,
    )
    test_logger: typing.Final = logger_factory()
    error_message: typing.Final = "error message"
    test_logger.error(error_message)
    assert error_message in test_stream.getvalue()


def test_fastapi_logging_bootstrap_working(minimal_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = FastApiLoggingInstrument(minimal_logging_config)

    fastapi_application: typing.Final = fastapi.FastAPI()

    @fastapi_application.get("/test-handler")
    async def test_handler() -> str:
        return "Ok"

    logging_instrument.bootstrap()
    logging_instrument.bootstrap_after(fastapi_application)

    with FastAPITestClient(app=fastapi_application) as test_client:
        test_client.get("/test-handler?test-query=1")
        test_client.get("/test-handler")
