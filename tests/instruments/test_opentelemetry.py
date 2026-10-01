import contextlib
import typing
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import fastapi
import litestar
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.testing import TestClient as LitestarTestClient
from opentelemetry import baggage, context
from opentelemetry.context import Context
from opentelemetry.instrumentation.dependencies import DependencyConflictError
from opentelemetry.sdk.trace import ReadableSpan, Span, TracerProvider
from opentelemetry.trace import SpanKind

from microbootstrap import OpentelemetryConfig, opentelemetry_baggage_scope
from microbootstrap.bootstrappers.fastapi import FastApiOpentelemetryInstrument
from microbootstrap.bootstrappers.litestar import (
    LitestarOpentelemetryInstrument,
    LitestarOpenTelemetryInstrumentationMiddleware,
)
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.opentelemetry_instrument import BaggageSpanProcessor, OpentelemetryInstrument


def test_opentelemetry_baggage_scope_overrides_removes_and_restores_values() -> None:
    outer_context = baggage.set_baggage("conversation_id", "outer-conversation", context=Context())
    outer_context = baggage.set_baggage("remove_me", "outer-value", context=outer_context)
    outer_token = context.attach(outer_context)

    try:
        with opentelemetry_baggage_scope(
            {
                "conversation_id": "inner-conversation",
                "existing_key": "existing-value",
                "remove_me": None,
            }
        ):
            assert baggage.get_baggage("conversation_id") == "inner-conversation"
            assert baggage.get_baggage("existing_key") == "existing-value"
            assert baggage.get_baggage("remove_me") is None

        assert baggage.get_baggage("conversation_id") == "outer-conversation"
        assert baggage.get_baggage("existing_key") is None
        assert baggage.get_baggage("remove_me") == "outer-value"
    finally:
        context.detach(outer_token)


def test_opentelemetry_baggage_scope_does_not_replace_exception_when_snapshot_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        opentelemetry_instrument,
        "snapshot_sentry_opentelemetry_baggage",
        Mock(side_effect=RuntimeError("snapshot failed")),
    )

    with (
        pytest.raises(ValueError, match="application error"),
        opentelemetry_baggage_scope({"conversation_id": "conversation-1"}),
    ):
        raise ValueError("application error")


def test_opentelemetry_baggage_scope_materializes_supplied_values_on_current_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = 42
    current_span = MagicMock(spec=Span)
    current_span.is_recording.return_value = True
    monkeypatch.setattr(opentelemetry_instrument, "get_current_span", Mock(return_value=current_span))

    with opentelemetry_baggage_scope(
        {"conversation_id": conversation_id, "not_configured": "ignored"},
        current_span_attributes={
            "conversation_id": "conversation.id",
            "not_supplied": "not.supplied",
        },
    ):
        assert baggage.get_baggage("conversation_id") == conversation_id

    current_span.set_attribute.assert_called_once_with("conversation.id", str(conversation_id))


@pytest.mark.parametrize(
    ("baggage_value", "is_recording"),
    [
        (None, True),
        ("conversation-1", False),
    ],
)
def test_opentelemetry_baggage_scope_skips_current_span_attribute(
    baggage_value: str | None,
    is_recording: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_span = MagicMock(spec=Span)
    current_span.is_recording.return_value = is_recording
    monkeypatch.setattr(opentelemetry_instrument, "get_current_span", Mock(return_value=current_span))

    with opentelemetry_baggage_scope(
        {"conversation_id": baggage_value},
        current_span_attributes={"conversation_id": "conversation.id"},
    ):
        pass

    current_span.set_attribute.assert_not_called()


@pytest.mark.parametrize(
    ("span_kind", "expected_attribute"),
    [
        (SpanKind.SERVER, True),
        (SpanKind.CONSUMER, True),
        (SpanKind.CLIENT, False),
        (SpanKind.PRODUCER, False),
        (SpanKind.INTERNAL, False),
    ],
)
def test_baggage_span_processor_materializes_allowed_server_and_consumer_attributes(
    span_kind: SpanKind,
    expected_attribute: bool,
) -> None:
    parent_context = baggage.set_baggage("conversation_id", "conversation-1", context=Context())
    parent_context = baggage.set_baggage("not_allowed", "secret", context=parent_context)
    span = MagicMock(spec=Span)
    span.kind = span_kind

    BaggageSpanProcessor({"conversation_id": "conversation_id"}).on_start(
        span,
        parent_context,
    )

    if expected_attribute:
        span.set_attribute.assert_called_once_with("conversation_id", "conversation-1")
    else:
        span.set_attribute.assert_not_called()


def test_baggage_span_processor_keeps_parent_contexts_isolated() -> None:
    processor = BaggageSpanProcessor({"conversation_id": "conversation_id"})
    first_context = baggage.set_baggage("conversation_id", "first", context=Context())
    second_context = baggage.set_baggage("conversation_id", "second", context=Context())
    first_span = MagicMock(spec=Span)
    second_span = MagicMock(spec=Span)
    first_span.kind = second_span.kind = SpanKind.CONSUMER

    processor.on_start(first_span, first_context)
    processor.on_start(second_span, second_context)

    first_span.set_attribute.assert_called_once_with("conversation_id", "first")
    second_span.set_attribute.assert_called_once_with("conversation_id", "second")

    processor.on_end(MagicMock(spec=ReadableSpan))


def test_opentelemetry_bootstrap_registers_baggage_span_processor(
    minimal_opentelemetry_config: OpentelemetryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer_provider = MagicMock(spec=TracerProvider)
    monkeypatch.setattr(opentelemetry_instrument, "SdkTracerProvider", Mock(return_value=tracer_provider))
    monkeypatch.setattr(opentelemetry_instrument, "set_tracer_provider", Mock())
    monkeypatch.setattr(opentelemetry_instrument, "entry_points", Mock(return_value=[]))
    minimal_opentelemetry_config.opentelemetry_endpoint = None
    minimal_opentelemetry_config.opentelemetry_baggage_span_attributes = {
        "conversation_id": "conversation_id",
    }

    OpentelemetryInstrument(minimal_opentelemetry_config).bootstrap()

    span_processor = tracer_provider.add_span_processor.call_args.args[0]
    assert isinstance(span_processor, BaggageSpanProcessor)
    assert span_processor.baggage_span_attributes == {
        "conversation_id": "conversation_id",
    }


def test_opentelemetry_is_ready(
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    test_opentelemetry_instrument: typing.Final = OpentelemetryInstrument(minimal_opentelemetry_config)
    assert test_opentelemetry_instrument.is_ready()


def test_opentelemetry_bootstrap_is_not_ready(minimal_opentelemetry_config: OpentelemetryConfig) -> None:
    minimal_opentelemetry_config.service_debug = False
    minimal_opentelemetry_config.opentelemetry_endpoint = None
    test_opentelemetry_instrument: typing.Final = OpentelemetryInstrument(minimal_opentelemetry_config)
    assert not test_opentelemetry_instrument.is_ready()


def test_opentelemetry_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    test_opentelemetry_instrument: typing.Final = OpentelemetryInstrument(minimal_opentelemetry_config)
    assert test_opentelemetry_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_opentelemetry_teardown(
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    test_opentelemetry_instrument: typing.Final = OpentelemetryInstrument(minimal_opentelemetry_config)
    assert test_opentelemetry_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_opentelemetry_bootstrap(
    minimal_opentelemetry_config: OpentelemetryConfig,
    magic_mock: MagicMock,
) -> None:
    minimal_opentelemetry_config.opentelemetry_instrumentors = [magic_mock]
    test_opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)

    test_opentelemetry_instrument.bootstrap()
    opentelemetry_bootstrap_result: typing.Final = test_opentelemetry_instrument.bootstrap_before()

    assert opentelemetry_bootstrap_result
    assert "middleware" in opentelemetry_bootstrap_result
    assert isinstance(opentelemetry_bootstrap_result["middleware"], list)
    assert len(opentelemetry_bootstrap_result["middleware"]) == 1
    assert isinstance(opentelemetry_bootstrap_result["middleware"][0], LitestarOpenTelemetryInstrumentationMiddleware)


def test_litestar_opentelemetry_teardown(
    minimal_opentelemetry_config: OpentelemetryConfig,
    magic_mock: MagicMock,
) -> None:
    minimal_opentelemetry_config.opentelemetry_instrumentors = [magic_mock]
    test_opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)

    test_opentelemetry_instrument.teardown()


def test_litestar_opentelemetry_bootstrap_working(
    minimal_opentelemetry_config: OpentelemetryConfig,
    async_mock: AsyncMock,
) -> None:
    test_opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)
    test_opentelemetry_instrument.bootstrap()
    opentelemetry_bootstrap_result: typing.Final = test_opentelemetry_instrument.bootstrap_before()

    opentelemetry_middleware = opentelemetry_bootstrap_result["middleware"][0]
    assert isinstance(opentelemetry_middleware, LitestarOpenTelemetryInstrumentationMiddleware)
    async_mock.__name__ = "test-name"
    opentelemetry_middleware.handle = async_mock  # type: ignore[method-assign]

    @litestar.get("/test-handler")
    async def test_handler() -> None:
        return None

    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[test_handler],
        **opentelemetry_bootstrap_result,
    )
    with LitestarTestClient(app=litestar_application) as test_client:
        # Silencing error, because we are mocking middleware call, so ASGI scope remains unchanged.
        with contextlib.suppress(AssertionError):
            test_client.get("/test-handler")
        assert async_mock.called


def test_fastapi_opentelemetry_bootstrap_working(
    minimal_opentelemetry_config: OpentelemetryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", Mock())

    test_opentelemetry_instrument: typing.Final = FastApiOpentelemetryInstrument(minimal_opentelemetry_config)
    test_opentelemetry_instrument.bootstrap()
    fastapi_application: typing.Final = test_opentelemetry_instrument.bootstrap_after(fastapi.FastAPI())

    @fastapi_application.get("/test-handler")
    async def test_handler() -> None:
        return None

    with patch("opentelemetry.trace.use_span") as mock_capture_event:
        FastAPITestClient(app=fastapi_application).get("/test-handler")
        assert mock_capture_event.called


@pytest.mark.parametrize(
    ("instruments", "result"),
    [
        (
            [
                MagicMock(),
                MagicMock(load=MagicMock(side_effect=ImportError)),
                MagicMock(load=MagicMock(side_effect=DependencyConflictError(mock.Mock()))),
                MagicMock(load=MagicMock(side_effect=ModuleNotFoundError)),
            ],
            "ok",
        ),
        (
            [
                MagicMock(load=MagicMock(side_effect=ValueError)),
            ],
            "raise",
        ),
        (
            [
                MagicMock(load=MagicMock(side_effect=ValueError)),
            ],
            "exclude",
        ),
    ],
)
def test_instrumentors_loader(
    minimal_opentelemetry_config: OpentelemetryConfig,
    instruments: list[MagicMock],
    result: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if result == "exclude":
        minimal_opentelemetry_config.opentelemetry_disabled_instrumentations = ["exclude_this", "exclude_that"]
        instruments[0].name = "exclude_this"
    monkeypatch.setattr(
        opentelemetry_instrument,
        "entry_points",
        MagicMock(return_value=[*instruments]),
    )

    if result != "raise":
        opentelemetry_instrument.OpentelemetryInstrument(instrument_config=minimal_opentelemetry_config).bootstrap()
        return

    with pytest.raises(ValueError):  # noqa: PT011
        opentelemetry_instrument.OpentelemetryInstrument(instrument_config=minimal_opentelemetry_config).bootstrap()
