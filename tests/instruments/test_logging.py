import logging
import typing
from io import StringIO

import litestar
from litestar.testing import AsyncTestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from microbootstrap import LoggingConfig
from microbootstrap.bootstrappers.litestar import LitestarLoggingInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument, MemoryLoggerFactory


def test_logging_is_ready(minimum_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimum_logging_config)
    assert logging_instrument.is_ready()


def test_logging_bootstrap_is_not_ready(minimum_logging_config: LoggingConfig) -> None:
    minimum_logging_config.service_debug = True
    logging_instrument: typing.Final = LoggingInstrument(minimum_logging_config)
    assert logging_instrument.bootstrap() == {}


def test_logging_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimum_logging_config: LoggingConfig,
) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimum_logging_config)
    assert logging_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_logging_teardown(
    minimum_logging_config: LoggingConfig,
) -> None:
    logging_instrument: typing.Final = LoggingInstrument(minimum_logging_config)
    assert logging_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_logging_bootstrap(minimum_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimum_logging_config)
    bootsrap_result: typing.Final = logging_instrument.bootstrap()
    assert "middleware" in bootsrap_result
    assert isinstance(bootsrap_result["middleware"], list)
    assert len(bootsrap_result["middleware"]) == 1


async def test_litestar_logging_bootstrap_working(minimum_logging_config: LoggingConfig) -> None:
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimum_logging_config)

    @litestar.get("/test-handler")
    async def error_handler() -> str:
        return "Ok"

    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[error_handler],
        **logging_instrument.bootstrap(),
    )

    async with AsyncTestClient(app=litestar_application) as async_client:
        await async_client.get("/test-handler?test-query=1")
        await async_client.get("/test-handler")


async def test_litestar_logging_bootstrap_tracer_injection(minimum_logging_config: LoggingConfig) -> None:
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    trace.get_tracer_provider().add_span_processor(span_processor)
    logging_instrument: typing.Final = LitestarLoggingInstrument(minimum_logging_config)

    @litestar.get("/test-handler")
    async def error_handler() -> str:
        return "Ok"

    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[error_handler],
        **logging_instrument.bootstrap(),
    )
    with tracer.start_as_current_span("my_fake_span") as span:
        # Do some fake work inside the span
        span.set_attribute("example_attribute", "value")
        span.add_event("example_event", {"event_attr": 1})
        async with AsyncTestClient(app=litestar_application) as async_client:
            await async_client.get("/test-handler")


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