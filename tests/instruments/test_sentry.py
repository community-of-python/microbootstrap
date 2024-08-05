import typing
from unittest.mock import MagicMock

import litestar
from litestar.testing import AsyncTestClient

from microbootstrap import SentryConfig
from microbootstrap.bootstrappers.litestar import LitestarSentryInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument


def test_sentry_is_ready(minimum_sentry_config: SentryConfig) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimum_sentry_config)
    assert sentry_instrument.is_ready()


def test_sentry_bootstrap_is_not_ready(minimum_sentry_config: SentryConfig) -> None:
    minimum_sentry_config.sentry_dsn = ""
    sentry_instrument: typing.Final = SentryInstrument(minimum_sentry_config)
    assert not sentry_instrument.is_ready()


def test_sentry_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimum_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimum_sentry_config)
    assert sentry_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_sentry_teardown(
    minimum_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = SentryInstrument(minimum_sentry_config)
    assert sentry_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_sentry_bootstrap(minimum_sentry_config: SentryConfig) -> None:
    sentry_instrument: typing.Final = LitestarSentryInstrument(minimum_sentry_config)

    sentry_instrument.bootstrap()
    assert sentry_instrument.bootstrap_before() == {
        "after_exception": [sentry_instrument.sentry_exception_catcher_hook],
    }


async def test_litestar_sentry_bootstrap_working(minimum_sentry_config: SentryConfig, magic_mock: MagicMock) -> None:
    sentry_instrument: typing.Final = LitestarSentryInstrument(minimum_sentry_config)
    sentry_instrument.sentry_exception_catcher_hook = magic_mock  # type: ignore[method-assign]

    @litestar.get("/test-error-handler")
    async def error_handler() -> None:
        raise ValueError("I'm test error")

    sentry_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[error_handler],
        **sentry_instrument.bootstrap_before(),
    )

    async with AsyncTestClient(app=litestar_application) as async_client:
        await async_client.get("/test-error-handler")
        assert magic_mock.called


async def test_litestar_sentry_bootstrap_catch_exception(
    minimum_sentry_config: SentryConfig,
) -> None:
    sentry_instrument: typing.Final = LitestarSentryInstrument(minimum_sentry_config)

    @litestar.get("/test-error-handler")
    async def error_handler() -> None:
        raise ValueError("I'm test error")

    sentry_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[error_handler],
        **sentry_instrument.bootstrap_before(),
    )

    async with AsyncTestClient(app=litestar_application) as async_client:
        await async_client.get("/test-error-handler")
