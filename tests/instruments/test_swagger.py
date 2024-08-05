import typing

import litestar
from litestar import openapi, status_codes
from litestar.static_files import StaticFilesConfig
from litestar.testing import AsyncTestClient

from microbootstrap.bootstrappers.litestar import LitestarSwaggerInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerConfig, SwaggerInstrument


def test_swagger_is_ready(minimum_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimum_swagger_config)
    assert swagger_instrument.is_ready()


def test_swagger_bootstrap_is_not_ready(minimum_swagger_config: SwaggerConfig) -> None:
    minimum_swagger_config.swagger_path = ""
    swagger_instrument: typing.Final = SwaggerInstrument(minimum_swagger_config)
    assert not swagger_instrument.is_ready()


def test_swagger_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimum_swagger_config: SwaggerConfig,
) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimum_swagger_config)
    assert swagger_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_swagger_teardown(
    minimum_swagger_config: SwaggerConfig,
) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimum_swagger_config)
    assert swagger_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_swagger_bootstrap_online_docs(minimum_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimum_swagger_config)

    swagger_instrument.bootstrap()
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()
    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert bootstrap_result["openapi_config"].title == minimum_swagger_config.service_name
    assert bootstrap_result["openapi_config"].version == minimum_swagger_config.service_version
    assert bootstrap_result["openapi_config"].description == minimum_swagger_config.service_description
    assert "static_files_config" not in bootstrap_result


def test_litestar_swagger_bootstrap_offline_docs(minimum_swagger_config: SwaggerConfig) -> None:
    minimum_swagger_config.swagger_offline_docs = True
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimum_swagger_config)

    swagger_instrument.bootstrap()
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()
    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert bootstrap_result["openapi_config"].title == minimum_swagger_config.service_name
    assert bootstrap_result["openapi_config"].version == minimum_swagger_config.service_version
    assert bootstrap_result["openapi_config"].description == minimum_swagger_config.service_description
    assert "static_files_config" in bootstrap_result
    assert isinstance(bootstrap_result["static_files_config"], list)
    assert len(bootstrap_result["static_files_config"]) == 1
    assert isinstance(bootstrap_result["static_files_config"][0], StaticFilesConfig)


async def test_litestar_swagger_bootstrap_working_online_docs(
    minimum_swagger_config: SwaggerConfig,
) -> None:
    minimum_swagger_config.swagger_path = "/my-docs-path"
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimum_swagger_config)

    swagger_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **swagger_instrument.bootstrap_before(),
    )

    async with AsyncTestClient(app=litestar_application) as async_client:
        response: typing.Final = await async_client.get(minimum_swagger_config.swagger_path)
        assert response.status_code == status_codes.HTTP_200_OK


async def test_litestar_swagger_bootstrap_working_offline_docs(
    minimum_swagger_config: SwaggerConfig,
) -> None:
    minimum_swagger_config.service_static_path = "/my-static-path"
    minimum_swagger_config.swagger_offline_docs = True
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimum_swagger_config)

    swagger_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **swagger_instrument.bootstrap_before(),
    )

    async with AsyncTestClient(app=litestar_application) as async_client:
        response = await async_client.get(minimum_swagger_config.swagger_path)
        assert response.status_code == status_codes.HTTP_200_OK
        response = await async_client.get(f"{minimum_swagger_config.service_static_path}/swagger-ui.css")
        assert response.status_code == status_codes.HTTP_200_OK
