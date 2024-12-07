import typing

import fastapi
import litestar
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import openapi, status_codes
from litestar.openapi import spec as litestar_openapi
from litestar.openapi.plugins import ScalarRenderPlugin
from litestar.static_files import StaticFilesConfig
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap.bootstrappers.fastapi import FastApiSwaggerInstrument
from microbootstrap.bootstrappers.litestar import LitestarSwaggerInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerConfig, SwaggerInstrument


def test_swagger_is_ready(minimal_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimal_swagger_config)
    assert swagger_instrument.is_ready()


def test_swagger_bootstrap_is_not_ready(minimal_swagger_config: SwaggerConfig) -> None:
    minimal_swagger_config.swagger_path = ""
    swagger_instrument: typing.Final = SwaggerInstrument(minimal_swagger_config)
    assert not swagger_instrument.is_ready()


def test_swagger_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_swagger_config: SwaggerConfig,
) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimal_swagger_config)
    assert swagger_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_swagger_teardown(
    minimal_swagger_config: SwaggerConfig,
) -> None:
    swagger_instrument: typing.Final = SwaggerInstrument(minimal_swagger_config)
    assert swagger_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_swagger_bootstrap_online_docs(minimal_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)

    swagger_instrument.bootstrap()
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()
    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert bootstrap_result["openapi_config"].title == minimal_swagger_config.service_name
    assert bootstrap_result["openapi_config"].version == minimal_swagger_config.service_version
    assert bootstrap_result["openapi_config"].description == minimal_swagger_config.service_description
    assert "static_files_config" not in bootstrap_result


def test_litestar_swagger_bootstrap_with_overridden_render_plugins(minimal_swagger_config: SwaggerConfig) -> None:
    new_render_plugins: typing.Final = [ScalarRenderPlugin()]
    minimal_swagger_config.swagger_extra_params["render_plugins"] = new_render_plugins

    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()

    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert bootstrap_result["openapi_config"].render_plugins is new_render_plugins


def test_litestar_swagger_bootstrap_extra_params_have_correct_types(minimal_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)
    new_components: typing.Final = litestar_openapi.Components(
        security_schemes={"Bearer": litestar_openapi.SecurityScheme(type="http", scheme="Bearer")}
    )
    swagger_instrument.configure_instrument(
        minimal_swagger_config.model_copy(update={"swagger_extra_params": {"components": new_components}})
    )
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()

    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert type(bootstrap_result["openapi_config"].components) is litestar_openapi.Components


def test_litestar_swagger_bootstrap_offline_docs(minimal_swagger_config: SwaggerConfig) -> None:
    minimal_swagger_config.swagger_offline_docs = True
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)

    swagger_instrument.bootstrap()
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()
    assert "openapi_config" in bootstrap_result
    assert isinstance(bootstrap_result["openapi_config"], openapi.OpenAPIConfig)
    assert bootstrap_result["openapi_config"].title == minimal_swagger_config.service_name
    assert bootstrap_result["openapi_config"].version == minimal_swagger_config.service_version
    assert bootstrap_result["openapi_config"].description == minimal_swagger_config.service_description
    assert "static_files_config" in bootstrap_result
    assert isinstance(bootstrap_result["static_files_config"], list)
    assert len(bootstrap_result["static_files_config"]) == 1
    assert isinstance(bootstrap_result["static_files_config"][0], StaticFilesConfig)


def test_litestar_swagger_bootstrap_working_online_docs(
    minimal_swagger_config: SwaggerConfig,
) -> None:
    minimal_swagger_config.swagger_path = "/my-docs-path"
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)

    swagger_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **swagger_instrument.bootstrap_before(),
    )

    with LitestarTestClient(app=litestar_application) as test_client:
        response: typing.Final = test_client.get(minimal_swagger_config.swagger_path)
        assert response.status_code == status_codes.HTTP_200_OK


def test_litestar_swagger_bootstrap_working_offline_docs(
    minimal_swagger_config: SwaggerConfig,
) -> None:
    minimal_swagger_config.service_static_path = "/my-static-path"
    minimal_swagger_config.swagger_offline_docs = True
    swagger_instrument: typing.Final = LitestarSwaggerInstrument(minimal_swagger_config)

    swagger_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **swagger_instrument.bootstrap_before(),
    )

    with LitestarTestClient(app=litestar_application) as test_client:
        response = test_client.get(minimal_swagger_config.swagger_path)
        assert response.status_code == status_codes.HTTP_200_OK
        response = test_client.get(f"{minimal_swagger_config.service_static_path}/swagger-ui.css")
        assert response.status_code == status_codes.HTTP_200_OK


def test_fastapi_swagger_bootstrap_online_docs(minimal_swagger_config: SwaggerConfig) -> None:
    swagger_instrument: typing.Final = FastApiSwaggerInstrument(minimal_swagger_config)
    bootstrap_result: typing.Final = swagger_instrument.bootstrap_before()
    assert bootstrap_result["title"] == minimal_swagger_config.service_name
    assert bootstrap_result["description"] == minimal_swagger_config.service_description
    assert bootstrap_result["docs_url"] == minimal_swagger_config.swagger_path
    assert bootstrap_result["version"] == minimal_swagger_config.service_version


def test_fastapi_swagger_bootstrap_working_online_docs(
    minimal_swagger_config: SwaggerConfig,
) -> None:
    minimal_swagger_config.swagger_path = "/my-docs-path"
    swagger_instrument: typing.Final = FastApiSwaggerInstrument(minimal_swagger_config)

    swagger_instrument.bootstrap()
    fastapi_application: typing.Final = fastapi.FastAPI(
        **swagger_instrument.bootstrap_before(),
    )

    response: typing.Final = FastAPITestClient(app=fastapi_application).get(minimal_swagger_config.swagger_path)
    assert response.status_code == status_codes.HTTP_200_OK


def test_fastapi_swagger_bootstrap_working_offline_docs(
    minimal_swagger_config: SwaggerConfig,
) -> None:
    minimal_swagger_config.service_static_path = "/my-static-path"
    minimal_swagger_config.swagger_offline_docs = True
    swagger_instrument: typing.Final = FastApiSwaggerInstrument(minimal_swagger_config)
    fastapi_application = fastapi.FastAPI(
        **swagger_instrument.bootstrap_before(),
    )
    swagger_instrument.bootstrap_after(fastapi_application)

    with FastAPITestClient(app=fastapi_application) as test_client:
        response = test_client.get(minimal_swagger_config.swagger_path)
        assert response.status_code == status_codes.HTTP_200_OK
        response = test_client.get(f"{minimal_swagger_config.service_static_path}/swagger-ui.css")
        assert response.status_code == status_codes.HTTP_200_OK
