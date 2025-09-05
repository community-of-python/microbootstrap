from __future__ import annotations
import copy
import typing
from unittest import mock
from unittest.mock import patch

import litestar
import pytest
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument, enrich_sentry_event_from_structlog_log


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
