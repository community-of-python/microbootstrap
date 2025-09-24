from __future__ import annotations
import copy
import typing
from unittest import mock

import litestar
import pytest
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.sentry_instrument import (
    SentryInstrument,
    add_trace_url_to_event,
    enrich_sentry_event_from_structlog_log,
)


if typing.TYPE_CHECKING:
    from sentry_sdk import _types as sentry_types

    from microbootstrap import SentryConfig


def test_sentry_is_ready(minimal_sentry_config: SentryConfig) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimal_sentry_config)
    assert sentry_instrument.is_ready()


def test_sentry_bootstrap_is_not_ready(minimal_sentry_config: SentryConfig) -> None:
    minimal_sentry_config.sentry_dsn = ""
    sentry_instrument: typing.Final = SentryInstrument(minimal_sentry_config)
    assert not sentry_instrument.is_ready()


def test_sentry_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimal_sentry_config)
    assert sentry_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_sentry_teardown(
    minimal_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimal_sentry_config)
    assert sentry_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_sentry_bootstrap(minimal_sentry_config: SentryConfig) -> None:
    sentry_instrument: typing.Final = LitestarSentryInstrument(minimal_sentry_config)
    sentry_instrument.bootstrap()
    assert sentry_instrument.bootstrap_before() == {}


def test_litestar_sentry_bootstrap_catch_exception(
    minimal_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = LitestarSentryInstrument(minimal_sentry_config)

    @litestar.get("/test-error-handler")
    async def error_handler() -> None:
        raise ValueError("I'm test error")

    sentry_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(route_handlers=[error_handler])
    with mock.patch("sentry_sdk.Scope.capture_event") as mock_capture_event:
        with LitestarTestClient(app=litestar_application) as test_client:
            test_client.get("/test-error-handler")

        assert mock_capture_event.called


class TestSentryEnrichEventFromStructlog:
    @pytest.mark.parametrize(
        "event",
        [
            {},
            {"logentry": None},
            {"logentry": {}},
            {"logentry": {"formatted": b""}},
            {"logentry": {"formatted": ""}},
            {"logentry": {"formatted": "hi"}},
            {"logentry": {"formatted": "[]"}},
            {"logentry": {"formatted": "[{}]"}},
            {"logentry": {"formatted": "{"}, "contexts": {}},
            {"logentry": {"formatted": "{}"}, "contexts": {}},
        ],
    )
    def test_skip(self, event: sentry_types.Event) -> None:
        assert enrich_sentry_event_from_structlog_log(copy.deepcopy(event), mock.Mock()) == event

    @pytest.mark.parametrize(
        ("event_before", "event_after"),
        [
            (
                {"logentry": {"formatted": '{"event": "event name"}'}, "contexts": {}},
                {"logentry": {"formatted": "event name"}, "contexts": {}},
            ),
            (
                {
                    "logentry": {
                        "formatted": '{"event": "event name", "timestamp": 1, "level": "error", "logger": "event.logger", "tracing": {}, "foo": "bar"}'  # noqa: E501
                    },
                    "contexts": {},
                },
                {
                    "logentry": {"formatted": "event name"},
                    "contexts": {"structlog": {"foo": "bar"}},
                },
            ),
        ],
    )
    def test_modify(self, event_before: sentry_types.Event, event_after: sentry_types.Event) -> None:
        assert enrich_sentry_event_from_structlog_log(event_before, mock.Mock()) == event_after


class MockSpanContext:
    def __init__(self, trace_id_hex: str) -> None:
        self.trace_id = int(trace_id_hex[:16], 16)  # Convert first 16 chars to int


class MockSpan:
    def __init__(self, is_recording: bool = True, trace_id_hex: str = "1234567890abcdef1234567890abcdef") -> None:
        self._is_recording = is_recording
        self._span_context = MockSpanContext(trace_id_hex)

    def is_recording(self) -> bool:
        return self._is_recording

    def get_span_context(self) -> MockSpanContext:
        return self._span_context


class TestSentryAddTraceUrlToEvent:
    def test_add_trace_url_with_trace_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        template = "https://example.com/traces/{trace_id}"
        trace_id = "1234567890abcdef1234567890abcdef"

        mock_trace = mock.Mock()
        mock_trace.get_current_span.return_value = MockSpan(True, trace_id)
        mock_trace.format_trace_id.return_value = trace_id
        monkeypatch.setattr("microbootstrap.instruments.sentry_instrument.trace", mock_trace)

        event: sentry_types.Event = {}
        result = add_trace_url_to_event(template, event, mock.Mock())
        assert result["contexts"]["tracing"]["trace_url"] == f"https://example.com/traces/{trace_id}"

    def test_add_trace_url_not_recording(self, monkeypatch: pytest.MonkeyPatch) -> None:
        template = "https://example.com/traces/{trace_id}"

        mock_trace = mock.Mock()
        mock_trace.get_current_span.return_value = MockSpan(False)
        monkeypatch.setattr("microbootstrap.instruments.sentry_instrument.trace", mock_trace)

        event: sentry_types.Event = {}
        result = add_trace_url_to_event(template, event, mock.Mock())
        assert "tracing" not in result.get("contexts", {})

    def test_add_trace_url_empty_template(self, monkeypatch: pytest.MonkeyPatch) -> None:
        template = ""
        trace_id = "1234567890abcdef1234567890abcdef"

        mock_trace = mock.Mock()
        mock_trace.get_current_span.return_value = MockSpan(True, trace_id)
        mock_trace.format_trace_id.return_value = trace_id
        monkeypatch.setattr("microbootstrap.instruments.sentry_instrument.trace", mock_trace)

        event: sentry_types.Event = {}
        result = add_trace_url_to_event(template, event, mock.Mock())
        assert "tracing" not in result.get("contexts", {})

    @pytest.mark.parametrize("event", [{}, {"contexts": {}}])
    def test_add_trace_url_creates_contexts(self, event: sentry_types.Event, monkeypatch: pytest.MonkeyPatch) -> None:
        template = "https://example.com/traces/{trace_id}"
        trace_id = "1234567890abcdef1234567890abcdef"

        mock_trace = mock.Mock()
        mock_trace.get_current_span.return_value = MockSpan(True, trace_id)
        mock_trace.format_trace_id.return_value = trace_id
        monkeypatch.setattr("microbootstrap.instruments.sentry_instrument.trace", mock_trace)

        result = add_trace_url_to_event(template, event, mock.Mock())
        assert "contexts" in result
        assert "tracing" in result["contexts"]
        assert "trace_url" in result["contexts"]["tracing"]
