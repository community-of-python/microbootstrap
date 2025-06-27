import contextlib
import typing
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import fastapi
import litestar
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.middleware.base import DefineMiddleware
from litestar.testing import TestClient as LitestarTestClient
from opentelemetry.instrumentation.dependencies import DependencyConflictError

from microbootstrap import OpentelemetryConfig
from microbootstrap.bootstrappers.fastapi import FastApiOpentelemetryInstrument
from microbootstrap.bootstrappers.litestar import LitestarOpentelemetryInstrument
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument


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
    assert isinstance(opentelemetry_bootstrap_result["middleware"][0], DefineMiddleware)


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
    assert isinstance(opentelemetry_middleware, DefineMiddleware)
    async_mock.__name__ = "test-name"
    opentelemetry_middleware.middleware.__call__ = async_mock  # type: ignore[operator]

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
                MagicMock(load=MagicMock(side_effect=DependencyConflictError("Hello"))),
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
