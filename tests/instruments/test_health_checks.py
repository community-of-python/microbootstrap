import typing

import fastapi
import litestar
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import status_codes
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap.bootstrappers.fastapi import FastApiHealthChecksInstrument
from microbootstrap.bootstrappers.litestar import LitestarHealthChecksInstrument
from microbootstrap.instruments.health_checks_instrument import (
    HealthChecksConfig,
    HealthChecksInstrument,
)


def test_health_checks_is_ready(minimal_health_checks_config: HealthChecksConfig) -> None:
    health_checks_instrument: typing.Final = HealthChecksInstrument(minimal_health_checks_config)
    assert health_checks_instrument.is_ready()


def test_health_checks_bootstrap_is_not_ready(minimal_health_checks_config: HealthChecksConfig) -> None:
    minimal_health_checks_config.health_checks_enabled = False
    health_checks_instrument: typing.Final = HealthChecksInstrument(minimal_health_checks_config)
    assert not health_checks_instrument.is_ready()


def test_health_checks_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_health_checks_config: HealthChecksConfig,
) -> None:
    health_checks_instrument: typing.Final = HealthChecksInstrument(minimal_health_checks_config)
    assert health_checks_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_health_checks_teardown(
    minimal_health_checks_config: HealthChecksConfig,
) -> None:
    health_checks_instrument: typing.Final = HealthChecksInstrument(minimal_health_checks_config)
    assert health_checks_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_health_checks_bootstrap() -> None:
    test_health_checks_path: typing.Final = "/test-path/"
    heatlh_checks_config: typing.Final = HealthChecksConfig(health_checks_path=test_health_checks_path)
    health_checks_instrument: typing.Final = LitestarHealthChecksInstrument(heatlh_checks_config)

    health_checks_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **health_checks_instrument.bootstrap_before(),
    )

    with LitestarTestClient(app=litestar_application) as async_client:
        response = async_client.get(heatlh_checks_config.health_checks_path)
        assert response.status_code == status_codes.HTTP_200_OK


def test_fastapi_health_checks_bootstrap() -> None:
    test_health_checks_path: typing.Final = "/test-path/"
    heatlh_checks_config: typing.Final = HealthChecksConfig(health_checks_path=test_health_checks_path)
    health_checks_instrument: typing.Final = FastApiHealthChecksInstrument(heatlh_checks_config)

    health_checks_instrument.bootstrap()
    fastapi_application = fastapi.FastAPI(
        **health_checks_instrument.bootstrap_before(),
    )
    fastapi_application = health_checks_instrument.bootstrap_after(fastapi_application)

    response = FastAPITestClient(app=fastapi_application).get(heatlh_checks_config.health_checks_path)
    assert response.status_code == status_codes.HTTP_200_OK
