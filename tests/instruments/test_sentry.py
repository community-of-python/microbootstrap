from __future__ import annotations
import copy
import logging
import typing
from unittest import mock

import fastapi
import litestar
import pytest
import sentry_sdk
import structlog
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.testing import TestClient as LitestarTestClient
from opentelemetry import baggage
from opentelemetry.context import Context, attach, detach

from microbootstrap import opentelemetry_baggage_scope
from microbootstrap.bootstrappers.fastapi import FastApiLoggingInstrument
from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.logging_instrument import LoggingConfig, LoggingInstrument
from microbootstrap.instruments.sentry_instrument import (
    SENTRY_EXTRA_OTEL_TRACE_ID_KEY,
    SENTRY_EXTRA_OTEL_TRACE_URL_KEY,
    SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE,
    SentryInstrument,
    SentryOpentelemetryBaggageIntegration,
    add_trace_url_to_event,
    enrich_sentry_event_from_opentelemetry_baggage,
    enrich_sentry_event_from_structlog_log,
)


if typing.TYPE_CHECKING:
    import faker
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


def test_fastapi_sentry_captures_unhandled_exception_with_traceback(
    minimal_logging_config: LoggingConfig,
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sentry_sdk.Scope.capture_event", capture_event := mock.Mock())
    SentryInstrument(minimal_sentry_config).bootstrap()
    fastapi_application: typing.Final = fastapi.FastAPI()

    @fastapi_application.get("/test-error-handler")
    async def error_handler() -> None:
        raise RuntimeError("test error")

    logging_instrument: typing.Final = FastApiLoggingInstrument(minimal_logging_config)
    logging_instrument.bootstrap()
    logging_instrument.bootstrap_after(fastapi_application)

    with FastAPITestClient(app=fastapi_application, raise_server_exceptions=False) as test_client:
        response: typing.Final = test_client.get("/test-error-handler")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    captured_events: typing.Final = [call.args[0] for call in capture_event.mock_calls]
    exception_events: typing.Final = [event for event in captured_events if event.get("exception")]
    assert len(exception_events) == 1
    exception_event: typing.Final = exception_events[0]
    exception_value: typing.Final = exception_event["exception"]["values"][-1]
    assert exception_value["type"] == "RuntimeError"
    assert exception_value["value"] == "test error"
    assert exception_value["stacktrace"]["frames"]


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


TRACE_URL_TEMPLATE = "https://example.com/traces/{trace_id}"
CONVERSATION_LOGS_URL_TEMPLATE = "https://example.com/logs/{conversation_id}"


def _configure_sentry_baggage_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    integration: typing.Final = SentryOpentelemetryBaggageIntegration(
        {"conversation_id"},
        {"conversation_id": CONVERSATION_LOGS_URL_TEMPLATE},
    )
    client = mock.Mock()
    client.get_integration.return_value = integration
    monkeypatch.setattr(sentry_sdk, "get_client", mock.Mock(return_value=client))


class TestSentryAddTraceUrlToEvent:
    def test_add_trace_url_with_trace_id(self, faker: faker.Faker) -> None:
        trace_id = faker.pystr()
        event: sentry_types.Event = {"extra": {SENTRY_EXTRA_OTEL_TRACE_ID_KEY: trace_id}}

        result = add_trace_url_to_event(TRACE_URL_TEMPLATE, event, mock.Mock())

        assert result["extra"][SENTRY_EXTRA_OTEL_TRACE_URL_KEY] == f"https://example.com/traces/{trace_id}"

    @pytest.mark.parametrize(
        "event",
        [
            {},
            {"extra": {}},
            {"extra": {"other_field": "value"}},
            {"extra": {SENTRY_EXTRA_OTEL_TRACE_ID_KEY: None}},
            {"extra": {SENTRY_EXTRA_OTEL_TRACE_ID_KEY: ""}},
        ],
    )
    def test_add_trace_url_without_trace_id(self, event: sentry_types.Event) -> None:
        result = add_trace_url_to_event(TRACE_URL_TEMPLATE, event, mock.Mock())

        assert SENTRY_EXTRA_OTEL_TRACE_URL_KEY not in result.get("extra", {})

    def test_add_trace_url_empty_template(self, faker: faker.Faker) -> None:
        event: sentry_types.Event = {"extra": {SENTRY_EXTRA_OTEL_TRACE_ID_KEY: faker.pystr()}}

        result = add_trace_url_to_event("", event, mock.Mock())

        assert SENTRY_EXTRA_OTEL_TRACE_URL_KEY not in result["extra"]

    @pytest.mark.parametrize("event", [{}, {"contexts": {}}])
    def test_add_trace_url_creates_contexts(self, faker: faker.Faker, event: sentry_types.Event) -> None:
        event["extra"] = {SENTRY_EXTRA_OTEL_TRACE_ID_KEY: faker.pystr()}

        result = add_trace_url_to_event(TRACE_URL_TEMPLATE, event, mock.Mock())

        assert SENTRY_EXTRA_OTEL_TRACE_URL_KEY in result["extra"]
        assert SENTRY_EXTRA_OTEL_TRACE_ID_KEY in result["extra"]


class TestSentryEnrichEventFromOpentelemetryBaggage:
    def test_returns_event_unchanged_without_configured_baggage(self) -> None:
        event: sentry_types.Event = {}

        result = enrich_sentry_event_from_opentelemetry_baggage(
            {"conversation_id"},
            {"conversation_id": "https://example.com/logs/{conversation_id}"},
            event,
            mock.Mock(),
        )

        assert result is event

    def test_adds_allowed_tag_and_encoded_url(self) -> None:
        context = baggage.set_baggage("conversation_id", "conversation/id +", context=Context())
        context = baggage.set_baggage("not_allowed", "secret", context=context)
        token = attach(context)
        event: sentry_types.Event = {"tags": {"existing": "tag"}, "extra": {"existing": "extra"}}

        try:
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {"conversation_id": "https://example.com/logs/{conversation_id}"},
                event,
                mock.Mock(),
            )
        finally:
            detach(token)

        assert result["tags"] == {"existing": "tag", "conversation_id": "conversation/id +"}
        assert result["extra"] == {
            "existing": "extra",
            "conversation_id_url": "https://example.com/logs/conversation%2Fid%20%2B",
        }

    def test_ignores_missing_denied_and_invalid_url_template(self) -> None:
        context = baggage.set_baggage("not_allowed", "secret", context=Context())
        token = attach(context)
        event: sentry_types.Event = {}

        try:
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {"not_allowed": "https://example.com/logs/without-placeholder"},
                event,
                mock.Mock(),
            )
        finally:
            detach(token)

        assert result == {}

    def test_keeps_attached_contexts_isolated(self) -> None:
        results = []
        for conversation_id in ("first", "second"):
            token = attach(baggage.set_baggage("conversation_id", conversation_id, context=Context()))
            try:
                result = enrich_sentry_event_from_opentelemetry_baggage(
                    {"conversation_id"},
                    {},
                    {},
                    mock.Mock(),
                )
            finally:
                detach(token)
            results.append(result)

        assert [result["tags"]["conversation_id"] for result in results] == ["first", "second"]

    @pytest.mark.parametrize(
        "hint",
        [
            {"exc_info": ()},
            {"exc_info": (RuntimeError, "not-an-exception", None)},
        ],
    )
    def test_invalid_exception_hint_falls_back_to_live_baggage(self, hint: sentry_types.Hint) -> None:
        with opentelemetry_baggage_scope({"conversation_id": "live"}):
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {},
                {},
                hint,
            )

        assert result["tags"]["conversation_id"] == "live"

    def test_uses_exception_snapshot_after_baggage_scope_detaches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_sentry_baggage_integration(monkeypatch)

        with (
            pytest.raises(RuntimeError) as exc_info,
            opentelemetry_baggage_scope(
                {
                    "conversation_id": "conversation/id +",
                    "not_allowed": "secret",
                }
            ),
        ):
            raise RuntimeError("test error")

        assert baggage.get_baggage("conversation_id") is None
        result = enrich_sentry_event_from_opentelemetry_baggage(
            {"conversation_id"},
            {"conversation_id": CONVERSATION_LOGS_URL_TEMPLATE},
            {},
            {"exc_info": (RuntimeError, exc_info.value, exc_info.value.__traceback__)},
        )

        assert result["tags"] == {"conversation_id": "conversation/id +"}
        assert result["extra"] == {
            "conversation_id_url": "https://example.com/logs/conversation%2Fid%20%2B",
        }
        assert getattr(exc_info.value, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE) == {
            "conversation_id": "conversation/id +",
        }

    def test_nested_baggage_scopes_keep_innermost_snapshot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_sentry_baggage_integration(monkeypatch)

        with (
            pytest.raises(RuntimeError) as exc_info,
            opentelemetry_baggage_scope({"conversation_id": "outer"}),
            opentelemetry_baggage_scope({"conversation_id": "inner"}),
        ):
            raise RuntimeError("test error")

        result = enrich_sentry_event_from_opentelemetry_baggage(
            {"conversation_id"},
            {},
            {},
            {"exc_info": (RuntimeError, exc_info.value, exc_info.value.__traceback__)},
        )

        assert result["tags"]["conversation_id"] == "inner"

    def test_unhashable_baggage_value_does_not_replace_original_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _configure_sentry_baggage_integration(monkeypatch)
        baggage_value: list[str] = ["conversation-1"]

        with (
            pytest.raises(RuntimeError, match="test error") as exc_info,
            opentelemetry_baggage_scope({"conversation_id": baggage_value}),
        ):
            raise RuntimeError("test error")

        assert getattr(exc_info.value, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE) == {
            "conversation_id": baggage_value,
        }

    def test_missing_snapshot_value_removes_stale_event_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_sentry_baggage_integration(monkeypatch)
        outer_token = attach(baggage.set_baggage("conversation_id", "parent", context=Context()))

        try:
            with pytest.raises(RuntimeError) as exc_info, opentelemetry_baggage_scope({"conversation_id": None}):
                raise RuntimeError("test error")

            assert baggage.get_baggage("conversation_id") == "parent"
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {"conversation_id": CONVERSATION_LOGS_URL_TEMPLATE},
                {
                    "tags": {"conversation_id": "stale", "existing": "tag"},
                    "extra": {"conversation_id_url": "stale", "existing": "extra"},
                },
                {"exc_info": (RuntimeError, exc_info.value, exc_info.value.__traceback__)},
            )
        finally:
            detach(outer_token)

        assert result["tags"] == {"existing": "tag"}
        assert result["extra"] == {"existing": "extra"}

    def test_caught_exception_snapshot_does_not_contaminate_later_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _configure_sentry_baggage_integration(monkeypatch)

        with pytest.raises(RuntimeError), opentelemetry_baggage_scope({"conversation_id": "caught"}):
            raise RuntimeError("caught error")

        with opentelemetry_baggage_scope({"conversation_id": "later"}):
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {},
                {},
                {},
            )

        assert result["tags"]["conversation_id"] == "later"

    def test_wrapped_exception_uses_first_snapshot_in_visible_chain(self) -> None:
        cause = RuntimeError("cause")
        setattr(cause, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE, {"conversation_id": "cause"})
        wrapper = ValueError("wrapper")
        wrapper.__cause__ = cause

        cause_result = enrich_sentry_event_from_opentelemetry_baggage(
            {"conversation_id"},
            {},
            {},
            {"exc_info": (ValueError, wrapper, None)},
        )
        setattr(wrapper, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE, {"conversation_id": "wrapper"})
        wrapper_result = enrich_sentry_event_from_opentelemetry_baggage(
            {"conversation_id"},
            {},
            {},
            {"exc_info": (ValueError, wrapper, None)},
        )

        assert cause_result["tags"]["conversation_id"] == "cause"
        assert wrapper_result["tags"]["conversation_id"] == "wrapper"

    def test_exception_chain_cycle_falls_back_to_live_baggage(self) -> None:
        exception = RuntimeError("cycle")
        exception.__cause__ = exception

        with opentelemetry_baggage_scope({"conversation_id": "live"}):
            result = enrich_sentry_event_from_opentelemetry_baggage(
                {"conversation_id"},
                {},
                {},
                {"exc_info": (RuntimeError, exception, None)},
            )

        assert result["tags"]["conversation_id"] == "live"

    def test_scope_without_sentry_integration_does_not_attach_snapshot(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = mock.Mock()
        client.get_integration.return_value = None
        monkeypatch.setattr(sentry_sdk, "get_client", mock.Mock(return_value=client))

        with (
            pytest.raises(RuntimeError) as exc_info,
            opentelemetry_baggage_scope({"conversation_id": "conversation-1"}),
        ):
            raise RuntimeError("test error")

        assert not hasattr(exc_info.value, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE)


def test_sentry_bootstrap_composes_baggage_enrichment_before_custom_callback(
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_before_send = mock.Mock(side_effect=lambda event, _hint: event)
    minimal_sentry_config.sentry_opentelemetry_baggage_keys = {"conversation_id"}
    minimal_sentry_config.sentry_opentelemetry_baggage_url_templates = {
        "conversation_id": CONVERSATION_LOGS_URL_TEMPLATE,
    }
    minimal_sentry_config.sentry_before_send = custom_before_send
    init = mock.Mock()
    monkeypatch.setattr("sentry_sdk.init", init)
    token = attach(baggage.set_baggage("conversation_id", "conversation-1", context=Context()))

    try:
        SentryInstrument(minimal_sentry_config).bootstrap()
        result = init.call_args.kwargs["before_send"]({}, mock.Mock())
    finally:
        detach(token)

    assert result["tags"]["conversation_id"] == "conversation-1"
    assert custom_before_send.call_args.args[0]["tags"]["conversation_id"] == "conversation-1"
    baggage_integration: typing.Final = next(
        integration
        for integration in init.call_args.kwargs["integrations"]
        if isinstance(integration, SentryOpentelemetryBaggageIntegration)
    )
    assert baggage_integration.baggage_keys == {"conversation_id"}
    assert baggage_integration.baggage_url_templates == {
        "conversation_id": CONVERSATION_LOGS_URL_TEMPLATE,
    }
    assert baggage_integration.setup_once() is None


@pytest.mark.parametrize("logger_instance", [structlog.get_logger(__name__), logging.getLogger(__name__)])
@pytest.mark.parametrize("is_exception", [True, False])
@pytest.mark.parametrize("service_debug", [True, False])
def test_sentry_captures_structlog_logs(  # noqa: PLR0913
    logger_instance: logging.Logger,
    is_exception: bool,
    service_debug: bool,
    monkeypatch: pytest.MonkeyPatch,
    faker: faker.Faker,
    minimal_sentry_config: SentryConfig,
) -> None:
    monkeypatch.setattr("sentry_sdk.Scope.capture_event", capture_mock := mock.Mock())
    SentryInstrument(minimal_sentry_config).bootstrap()
    LoggingInstrument(LoggingConfig(service_debug=service_debug)).bootstrap()

    if is_exception:
        try:
            _ = 1 / 0
        except ZeroDivisionError:
            logger_instance.exception("in exception")
    else:
        logger_instance.error(faker.pystr())

    assert capture_mock.mock_calls
    if service_debug:
        assert bool(capture_mock.mock_calls[0].args[0].get("exception")) == is_exception
