from __future__ import annotations
import copy
import typing
from unittest import mock

import faker
import litestar
import pytest
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.sentry_instrument import (
    SENTRY_EXTRA_OTEL_TRACE_ID_KEY,
    SENTRY_EXTRA_OTEL_TRACE_URL_KEY,
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
