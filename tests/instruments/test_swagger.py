import typing

import fastapi
import litestar
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import openapi, status_codes
from litestar.openapi import spec as litestar_openapi
from litestar.openapi.plugins import ScalarRenderPlugin
from litestar.static_files import StaticFilesConfig
from litestar.testing import TestClient as LitestarTestClient
from pydantic import ValidationError

from microbootstrap.bootstrappers.fastapi import FastApiSwaggerInstrument
from microbootstrap.bootstrappers.litestar import LitestarSwaggerInstrument
from microbootstrap.instruments.openapi_security_schemes import OpenApiHttpSecurityScheme
from microbootstrap.instruments.openapi_version_docs import OpenApiOperationVersionOverride, OpenApiVersionDocsConfig
from microbootstrap.instruments.swagger_instrument import SwaggerConfig, SwaggerInstrument
from microbootstrap.settings import FastApiSettings, LitestarSettings


TARGET_PATH: typing.Final = "/widgets"


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
    swagger_instrument.teardown()


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
        response = test_client.get(f"{minimal_swagger_config.service_static_path}/swagger-ui-bundle.js")
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
        response = test_client.get(f"{minimal_swagger_config.service_static_path}/swagger-ui-bundle.js")
        assert response.status_code == status_codes.HTTP_200_OK


@pytest.mark.parametrize(
    ("configuration", "error"),
    [
        (
            lambda: OpenApiVersionDocsConfig.model_validate({"vendor_media_type": "application/vnd.example+json"}),
            "Field required",
        ),
        (
            lambda: OpenApiVersionDocsConfig.model_validate({"supported_versions": ("2026-01",)}),
            "Field required",
        ),
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type=None,
                supported_versions=("2026-01",),
            ),
            "Input should be a valid string",
        ),
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type="application/vnd.example+json",
                supported_versions=None,
            ),
            "Input should be a valid tuple",
        ),
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type="application/json",
                supported_versions=("1.0",),
            ),
            "Vendor media type must use",
        ),
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type="application/vnd.example+json",
                supported_versions=("1.0", "1.0"),
            ),
            "must not contain duplicates",
        ),
        (
            lambda: OpenApiOperationVersionOverride(path="widgets", method="get", supported_versions=()),
            "must be an absolute path",
        ),
        (
            lambda: OpenApiOperationVersionOverride(path="/widgets", method="GET", supported_versions=()),
            "Operation method must be one of",
        ),
    ],
)
def test_openapi_version_docs_configuration_rejects_invalid_values(
    configuration: typing.Callable[[], object],
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        configuration()


@pytest.mark.parametrize("enabled", [False, True])
def test_openapi_version_docs_rejects_removed_enabled_field(enabled: bool) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OpenApiVersionDocsConfig.model_validate(
            {"enabled": enabled, "vendor_media_type": "application/vnd.example+json", "supported_versions": ("1.0",)}
        )


def test_openapi_version_docs_rejects_removed_suppression_and_unknown_override_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OpenApiVersionDocsConfig.model_validate(
            {
                "vendor_media_type": "application/vnd.example+json",
                "supported_versions": ("1.0",),
                "suppressed_operations": (),
            }
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OpenApiOperationVersionOverride.model_validate(
            {"path": "/widgets", "method": "get", "supported_versions": (), "enabled": False}
        )


@pytest.mark.parametrize(
    "vendor_media_type",
    [
        "",
        "version1.0",
        "application/json",
        "application/vnd.+json",
        "application/vnd.example api+json",
        "application/vnd.bad name+json",
        "application/vnd.example\tapi+json",
        "application/vnd.example\napi+json",
        "application/vnd.example\x00api+json",
        "application/vnd.example`api+json",
        "application/vnd.example,api+json",
        "application/vnd.example;api+json",
    ],
)
def test_openapi_version_docs_rejects_unsafe_vendor_media_types(vendor_media_type: str) -> None:
    with pytest.raises(ValidationError, match="Vendor media type must use"):
        OpenApiVersionDocsConfig(
            vendor_media_type=vendor_media_type,
            supported_versions=("release-2026",),
        )


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1.0 ",
        "1.0\tnext",
        "1.0\nnext",
        "1.0\x00next",
        "1.0`next",
        "1.0,next",
        "1.0;next",
        "version1.0, application/json",
    ],
)
def test_openapi_version_docs_rejects_unsafe_versions(version: str) -> None:
    with pytest.raises(ValidationError, match="safe media-type token"):
        OpenApiVersionDocsConfig(
            vendor_media_type="application/vnd.real-api+json",
            supported_versions=(version,),
        )


def test_openapi_version_docs_accepts_real_vendor_and_non_semver_versions() -> None:
    configuration: typing.Final = OpenApiVersionDocsConfig(
        vendor_media_type="application/vnd.real-api_v2+json",
        supported_versions=("2026-01", "release-candidate", "v1.0+beta"),
    )

    assert configuration.vendor_media_type == "application/vnd.real-api_v2+json"
    assert configuration.supported_versions == ("2026-01", "release-candidate", "v1.0+beta")


def test_openapi_version_docs_accepts_explicit_empty_operation_override_versions() -> None:
    configuration: typing.Final = OpenApiOperationVersionOverride(
        path="/widgets",
        method="get",
        supported_versions=(),
    )

    assert configuration.supported_versions == ()


@pytest.mark.parametrize("settings_type", [FastApiSettings, LitestarSettings])
def test_settings_validate_security_schemes_and_operation_versions(
    settings_type: type[FastApiSettings] | type[LitestarSettings],
) -> None:
    settings = settings_type(
        security_schemes={"serviceBearer": {"type": "http", "scheme": "bearer"}},
        openapi_version_docs={
            "vendor_media_type": "application/vnd.real-api+json",
            "supported_versions": ("2026-01",),
            "operation_versions": ({"path": TARGET_PATH, "method": "post", "supported_versions": ("2027-01",)},),
        },
    )
    assert settings.security_schemes == {"serviceBearer": OpenApiHttpSecurityScheme(scheme="bearer")}
    assert settings.openapi_version_docs is not None
    assert settings.openapi_version_docs.operation_versions[0].supported_versions == ("2027-01",)


@pytest.mark.parametrize(
    ("configuration", "message"),
    [
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type="application/vnd.real-api+json",
                supported_versions=(),
            ),
            "requires at least one supported API version",
        ),
        (
            lambda: OpenApiVersionDocsConfig(
                vendor_media_type="application/vnd.real-api+json",
                supported_versions=("2026-01",),
                operation_versions=(
                    OpenApiOperationVersionOverride(
                        path=TARGET_PATH,
                        method="post",
                        supported_versions=("2027-01",),
                    ),
                    OpenApiOperationVersionOverride(
                        path=TARGET_PATH,
                        method="post",
                        supported_versions=("2028-01",),
                    ),
                ),
            ),
            "duplicate path and method pairs",
        ),
    ],
)
def test_version_docs_settings_reject_empty_global_versions_and_duplicate_override_selectors(
    configuration: typing.Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        configuration()
