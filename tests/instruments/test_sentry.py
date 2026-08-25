from __future__ import annotations
import copy
import logging
import typing
from unittest import mock

import litestar
import pytest
import structlog
from litestar.testing import TestClient as LitestarTestClient
from opentelemetry import baggage
from opentelemetry.context import Context, attach, detach

from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.logging_instrument import LoggingConfig, LoggingInstrument
from microbootstrap.instruments.sentry_instrument import (
    SENTRY_EXTRA_OTEL_TRACE_ID_KEY,
    SENTRY_EXTRA_OTEL_TRACE_URL_KEY,
    SentryInstrument,
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


def test_sentry_bootstrap_composes_baggage_enrichment_before_custom_callback(
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_before_send = mock.Mock(side_effect=lambda event, _hint: event)
    minimal_sentry_config.sentry_opentelemetry_baggage_keys = {"conversation_id"}
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
