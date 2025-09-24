from __future__ import annotations
import copy
import typing
from unittest import mock
from unittest.mock import patch

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
    with patch("sentry_sdk.Scope.capture_event") as mock_capture_event:
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


class TestSentryAddTraceUrlToEvent:
    def test_add_trace_url_with_trace_id(self) -> None:
        template = "https://example.com/traces/{trace_id}"
        trace_id = "1234567890abcdef1234567890abcdef"

        # Mock the OpenTelemetry trace functions
        with patch("microbootstrap.instruments.sentry_instrument.trace") as mock_trace:
            # Create a mock span context
            mock_span_context = mock.Mock()
            mock_span_context.trace_id = int(trace_id[:16], 16)  # Convert first 16 chars to int

            # Create a mock span
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = True
            mock_span.get_span_context.return_value = mock_span_context

            # Mock the format_trace_id function to return our trace_id
            mock_trace.format_trace_id.return_value = trace_id
            mock_trace.get_current_span.return_value = mock_span

            event: sentry_types.Event = {}
            result = add_trace_url_to_event(template, event, mock.Mock())
            assert result["contexts"]["tracing"]["trace_url"] == f"https://example.com/traces/{trace_id}"

    def test_add_trace_url_grafana_template(self) -> None:
        template = "https://example.com/explore?query={trace_id}"
        trace_id = "1234567890abcdef1234567890abcdef"

        # Mock the OpenTelemetry trace functions
        with patch("microbootstrap.instruments.sentry_instrument.trace") as mock_trace:
            # Create a mock span context
            mock_span_context = mock.Mock()
            mock_span_context.trace_id = int(trace_id[:16], 16)  # Convert first 16 chars to int

            # Create a mock span
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = True
            mock_span.get_span_context.return_value = mock_span_context

            # Mock the format_trace_id function to return our trace_id
            mock_trace.format_trace_id.return_value = trace_id
            mock_trace.get_current_span.return_value = mock_span

            event: sentry_types.Event = {}
            result = add_trace_url_to_event(template, event, mock.Mock())
            assert result["contexts"]["tracing"]["trace_url"] == f"https://example.com/explore?query={trace_id}"

    @pytest.mark.parametrize("is_recording", [False, True])
    def test_add_trace_url_no_trace_url_added(self, is_recording: bool) -> None:
        template = "https://example.com/traces/{trace_id}"

        # Mock the OpenTelemetry trace functions
        with patch("microbootstrap.instruments.sentry_instrument.trace") as mock_trace:
            # Create a mock span
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = is_recording
            mock_trace.get_current_span.return_value = mock_span

            # When not recording, we shouldn't add anything
            # When recording but no trace_id, we still shouldn't add anything
            if not is_recording:
                mock_trace.get_current_span.return_value = mock_span
            else:
                # Create a mock span context for the recording case
                mock_span_context = mock.Mock()
                mock_span_context.trace_id = int("1234567890abcdef", 16)
                mock_span.get_span_context.return_value = mock_span_context
                mock_trace.format_trace_id.return_value = "1234567890abcdef1234567890abcdef"

            event: sentry_types.Event = {}
            result = add_trace_url_to_event(template, event, mock.Mock())

            if not is_recording:
                # When not recording, no tracing context should be added
                assert "tracing" not in result.get("contexts", {})
            else:
                # When recording, the tracing context should be added
                assert "tracing" in result["contexts"]

    def test_add_trace_url_empty_template(self) -> None:
        template = ""
        trace_id = "1234567890abcdef1234567890abcdef"

        # Mock the OpenTelemetry trace functions
        with patch("microbootstrap.instruments.sentry_instrument.trace") as mock_trace:
            # Create a mock span context
            mock_span_context = mock.Mock()
            mock_span_context.trace_id = int(trace_id[:16], 16)  # Convert first 16 chars to int

            # Create a mock span
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = True
            mock_span.get_span_context.return_value = mock_span_context

            # Mock the format_trace_id function to return our trace_id
            mock_trace.format_trace_id.return_value = trace_id
            mock_trace.get_current_span.return_value = mock_span

            event: sentry_types.Event = {}
            result = add_trace_url_to_event(template, event, mock.Mock())
            # With empty template, no trace_url should be added
            assert "trace_url" not in result.get("contexts", {}).get("tracing", {})

    def test_add_trace_url_creates_contexts_if_missing(self) -> None:
        template = "https://example.com/traces/{trace_id}"
        trace_id = "1234567890abcdef1234567890abcdef"

        # Mock the OpenTelemetry trace functions
        with patch("microbootstrap.instruments.sentry_instrument.trace") as mock_trace:
            # Create a mock span context
            mock_span_context = mock.Mock()
            mock_span_context.trace_id = int(trace_id[:16], 16)  # Convert first 16 chars to int

            # Create a mock span
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = True
            mock_span.get_span_context.return_value = mock_span_context

            # Mock the format_trace_id function to return our trace_id
            mock_trace.format_trace_id.return_value = trace_id
            mock_trace.get_current_span.return_value = mock_span

            event: sentry_types.Event = {}
            result = add_trace_url_to_event(template, event, mock.Mock())
            assert "contexts" in result
            assert "tracing" in result["contexts"]
            assert "trace_url" in result["contexts"]["tracing"]
