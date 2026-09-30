import copy
import dataclasses
import typing
from unittest.mock import MagicMock

import fastapi
import litestar
import pytest
from fastapi.security import HTTPBearer
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import get, openapi, post, status_codes
from litestar.openapi import spec as litestar_openapi
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.testing import TestClient as LitestarTestClient
from pydantic import BaseModel

from microbootstrap import (
    OpenApiApiKeySecurityScheme,
    OpenApiHttpSecurityScheme,
    OpenApiOAuth2SecurityScheme,
    OpenApiOAuthFlow,
    OpenApiOAuthFlows,
    OpenApiOpenIdConnectSecurityScheme,
    OpenApiOperationSelector,
    OpenApiOperationVersionOverride,
    OpenApiSecurityScheme,
    OpenApiVersionDocsConfig,
    SwaggerConfig,
)
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper, FastApiSwaggerInstrument
from microbootstrap.bootstrappers.fastapi import add_security_schemes as add_fastapi_security_schemes
from microbootstrap.bootstrappers.litestar import (
    LitestarBootstrapper,
    LitestarSwaggerInstrument,
    add_accept_versioning_extension,
)
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.openapi_security_schemes import serialize_security_schemes
from microbootstrap.settings import FastApiSettings, LitestarSettings


TARGET_PATH: typing.Final = "/widgets"
UNCHANGED_PATH: typing.Final = "/service-health"
MISSING_DESCRIPTION_PATH: typing.Final = "/without-description"
VERSION_DOCUMENTATION: typing.Final = (
    "Supported API versions:\n"
    "- `application/vnd.real-api+json; version=2026-01`.\n"
    "- `application/vnd.real-api+json; version=release-candidate`."
)
GET_DESCRIPTION: typing.Final = "List widgets"
POST_DESCRIPTION: typing.Final = "Create widget"
LATE_OPERATION_DESCRIPTION: typing.Final = "Changed after the schema was first served"
EXPECTED_GENERATOR_CALLS: typing.Final = 2


class ServiceOwnedResponse(BaseModel):
    status: str


@dataclasses.dataclass
class BuiltSwaggerApplication:
    framework: str
    application: fastapi.FastAPI | litestar.Litestar
    schema_path: str
    renderer: SwaggerRenderPlugin | None = None

    def schema(self) -> dict[str, typing.Any]:
        if isinstance(self.application, litestar.Litestar):
            assert self.application.openapi_schema is not None
            return self.application.openapi_schema.to_schema()
        return self.application.openapi()


@pytest.fixture(params=("fastapi", "litestar"))
def swagger_framework(request: pytest.FixtureRequest) -> str:
    return typing.cast("str", request.param)


def build_version_docs_config(
    suppressed_operations: tuple[OpenApiOperationSelector, ...] = (),
    operation_versions: tuple[OpenApiOperationVersionOverride, ...] = (),
) -> OpenApiVersionDocsConfig:
    return OpenApiVersionDocsConfig(
        enabled=True,
        vendor_media_type="application/vnd.real-api+json",
        supported_versions=("2026-01", "release-candidate"),
        suppressed_operations=suppressed_operations,
        operation_versions=operation_versions,
    )


def build_expected_description(description: object, supported_versions: tuple[str, ...]) -> str:
    version_documentation = "\n".join(
        f"- `application/vnd.real-api+json; version={version}`." for version in supported_versions
    )
    if len(supported_versions) == 1:
        version_documentation = version_documentation.removeprefix("- ").removesuffix(".") + "."
        version_documentation = f"Supported API version: {version_documentation}"
    else:
        version_documentation = f"Supported API versions:\n{version_documentation}"
    if not isinstance(description, str) or not description:
        return version_documentation
    return f"{description}\n\n{version_documentation}"


def build_expected_documented_schema(
    original_schema: dict[str, typing.Any],
    configuration: OpenApiVersionDocsConfig,
) -> dict[str, typing.Any]:
    expected_schema: typing.Final = copy.deepcopy(original_schema)
    suppressed_pairs: typing.Final = {
        (selector.path, selector.method) for selector in configuration.suppressed_operations
    }
    overrides: typing.Final = {
        (override.path, override.method): override.supported_versions for override in configuration.operation_versions
    }
    for path, path_item in expected_schema["paths"].items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in {"delete", "get", "head", "options", "patch", "post", "put", "trace"}:
                continue
            if (path, method) in suppressed_pairs or not isinstance(operation, dict):
                continue
            supported_versions = overrides.get((path, method), configuration.supported_versions)
            operation["description"] = build_expected_description(operation.get("description"), supported_versions)
            operation["x-accept-versioning"] = {
                "header": "Accept",
                "mediaType": configuration.vendor_media_type,
                "parameter": "version",
                "supportedVersions": list(supported_versions),
            }
    return expected_schema


def build_litestar_application(
    version_docs_config: OpenApiVersionDocsConfig | None,
    startup_hook: MagicMock | None = None,
    shutdown_hook: MagicMock | None = None,
    security_schemes: dict[str, OpenApiSecurityScheme] | None = None,
) -> BuiltSwaggerApplication:
    @get(TARGET_PATH, description=GET_DESCRIPTION, security=[{"ServiceAuth": []}])
    async def list_widgets() -> ServiceOwnedResponse:
        return ServiceOwnedResponse(status="ok")

    @post(TARGET_PATH, description=POST_DESCRIPTION)
    async def create_widget() -> ServiceOwnedResponse:
        return ServiceOwnedResponse(status="created")

    @get(UNCHANGED_PATH, description="Service health")
    async def service_health() -> dict[str, str]:
        return {"status": "ok"}

    @get(MISSING_DESCRIPTION_PATH)
    async def list_widgets_without_description() -> dict[str, str]:
        return {"status": "ok"}

    renderer: typing.Final = SwaggerRenderPlugin()
    service_owned_components: typing.Final = litestar_openapi.Components(
        security_schemes={
            "GlobalAuth": litestar_openapi.SecurityScheme(type="http", scheme="bearer"),
            "ServiceAuth": litestar_openapi.SecurityScheme(type="http", scheme="bearer"),
        },
    )
    application: typing.Final = (
        LitestarBootstrapper(
            LitestarSettings(
                service_debug=False,
                security_schemes=security_schemes or {},
                openapi_version_docs=version_docs_config,
            )
        )
        .configure_application(
            LitestarConfig(
                route_handlers=[list_widgets, create_widget, service_health, list_widgets_without_description],
                on_startup=[startup_hook] if startup_hook is not None else [],
                on_shutdown=[shutdown_hook] if shutdown_hook is not None else [],
                openapi_config=openapi.OpenAPIConfig(
                    title="Service API",
                    version="1.0.0",
                    components=service_owned_components,
                    security=[{"GlobalAuth": []}],
                    render_plugins=[renderer],
                ),
            )
        )
        .bootstrap()
    )
    return BuiltSwaggerApplication("litestar", application, "/schema/openapi.json", renderer)


def build_fastapi_application(
    version_docs_config: OpenApiVersionDocsConfig | None,
    security_schemes: dict[str, OpenApiSecurityScheme] | None = None,
) -> BuiltSwaggerApplication:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(
            service_debug=False,
            security_schemes=security_schemes or {},
            openapi_version_docs=version_docs_config,
        )
    ).bootstrap()
    service_authentication: typing.Final = HTTPBearer()

    @application.get(TARGET_PATH, description=GET_DESCRIPTION, dependencies=[fastapi.Security(service_authentication)])
    async def list_widgets() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(TARGET_PATH, description=POST_DESCRIPTION)
    async def create_widget() -> dict[str, str]:
        return {"status": "created"}

    @application.get(UNCHANGED_PATH, description="Service health")
    async def service_health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(MISSING_DESCRIPTION_PATH)
    async def list_widgets_without_description() -> dict[str, str]:
        return {"status": "ok"}

    return BuiltSwaggerApplication("fastapi", application, "/openapi.json")


def build_application(
    framework: str,
    version_docs_config: OpenApiVersionDocsConfig | None,
    security_schemes: dict[str, OpenApiSecurityScheme] | None = None,
) -> BuiltSwaggerApplication:
    if framework == "litestar":
        return build_litestar_application(version_docs_config, security_schemes=security_schemes)
    return build_fastapi_application(version_docs_config, security_schemes)


def request_schema(application: BuiltSwaggerApplication) -> dict[str, typing.Any]:
    if application.framework == "litestar":
        assert isinstance(application.application, litestar.Litestar)
        with LitestarTestClient(app=application.application) as test_client:
            response = test_client.get(application.schema_path)
    else:
        assert isinstance(application.application, fastapi.FastAPI)
        with FastAPITestClient(app=application.application) as test_client:
            response = test_client.get(application.schema_path)
    assert response.status_code == status_codes.HTTP_200_OK
    return typing.cast("dict[str, typing.Any]", response.json())


def create_widget(application: BuiltSwaggerApplication) -> None:
    expected_status: int
    if application.framework == "litestar":
        assert isinstance(application.application, litestar.Litestar)
        with LitestarTestClient(app=application.application) as test_client:
            response = test_client.post(TARGET_PATH)
        expected_status = status_codes.HTTP_201_CREATED
    else:
        assert isinstance(application.application, fastapi.FastAPI)
        with FastAPITestClient(app=application.application) as test_client:
            response = test_client.post(TARGET_PATH)
        expected_status = status_codes.HTTP_200_OK
    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "created"}


def test_production_version_docs_only_change_expected_operation_descriptions(swagger_framework: str) -> None:
    suppressed_operations: typing.Final = (OpenApiOperationSelector(path=TARGET_PATH, method="get"),)
    baseline_application: typing.Final = build_application(swagger_framework, None)
    original_schema: typing.Final = baseline_application.schema()
    version_docs_config: typing.Final = build_version_docs_config(suppressed_operations)
    application: typing.Final = build_application(swagger_framework, version_docs_config)
    expected_schema: typing.Final = build_expected_documented_schema(original_schema, version_docs_config)

    early_schema: typing.Final = application.schema()
    repeated_schema: typing.Final = application.schema()
    first_served_schema: typing.Final = request_schema(application)
    second_served_schema: typing.Final = request_schema(application)

    assert early_schema == expected_schema
    assert repeated_schema == expected_schema
    assert first_served_schema == expected_schema
    assert second_served_schema == expected_schema
    assert early_schema["components"] == original_schema["components"]
    assert early_schema.get("security") == original_schema.get("security")
    assert early_schema["paths"][TARGET_PATH]["get"] == original_schema["paths"][TARGET_PATH]["get"]
    assert early_schema["paths"][TARGET_PATH]["post"]["description"] == build_expected_description(
        POST_DESCRIPTION,
        version_docs_config.supported_versions,
    )
    assert early_schema["paths"][MISSING_DESCRIPTION_PATH]["get"]["description"] == VERSION_DOCUMENTATION
    assert early_schema["paths"][TARGET_PATH]["post"]["description"].count(VERSION_DOCUMENTATION) == 1
    assert "x-accept-versioning" not in early_schema["paths"][TARGET_PATH]["get"]
    assert early_schema["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == {
        "header": "Accept",
        "mediaType": "application/vnd.real-api+json",
        "parameter": "version",
        "supportedVersions": ["2026-01", "release-candidate"],
    }
    create_widget(application)


@pytest.mark.parametrize("version_docs_config", [None, OpenApiVersionDocsConfig()])
def test_absent_or_disabled_version_docs_preserve_the_whole_schema(
    swagger_framework: str,
    version_docs_config: OpenApiVersionDocsConfig | None,
) -> None:
    baseline_application: typing.Final = build_application(swagger_framework, None)
    baseline_schema: typing.Final = baseline_application.schema()
    application: typing.Final = build_application(swagger_framework, version_docs_config)

    assert application.schema() == baseline_schema
    assert request_schema(application) == baseline_schema
    create_widget(application)


def test_production_version_docs_use_singular_format_for_one_supported_version(swagger_framework: str) -> None:
    configuration: typing.Final = OpenApiVersionDocsConfig(
        enabled=True,
        vendor_media_type="application/vnd.real-api+json",
        supported_versions=("2026-01",),
    )
    application: typing.Final = build_application(swagger_framework, configuration)

    assert application.schema()["paths"][TARGET_PATH]["post"]["description"] == (
        f"{POST_DESCRIPTION}\n\nSupported API version: `application/vnd.real-api+json; version=2026-01`."
    )


def test_operation_version_override_and_accept_requests_do_not_change_runtime(swagger_framework: str) -> None:
    version_docs_config: typing.Final = build_version_docs_config(
        operation_versions=(
            OpenApiOperationVersionOverride(
                path=TARGET_PATH,
                method="post",
                supported_versions=("2027-01",),
            ),
        ),
    )
    baseline_application: typing.Final = build_application(swagger_framework, None)
    baseline_schema: typing.Final = baseline_application.schema()
    application: typing.Final = build_application(swagger_framework, version_docs_config)
    schema: typing.Final = application.schema()

    assert schema["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == {
        "header": "Accept",
        "mediaType": "application/vnd.real-api+json",
        "parameter": "version",
        "supportedVersions": ["2027-01"],
    }
    assert schema["paths"][TARGET_PATH]["post"]["description"] == build_expected_description(
        POST_DESCRIPTION,
        ("2027-01",),
    )
    assert schema["paths"][TARGET_PATH]["post"].get("parameters") == baseline_schema["paths"][TARGET_PATH]["post"].get(
        "parameters"
    )
    assert schema["paths"][TARGET_PATH]["post"].get("responses") == baseline_schema["paths"][TARGET_PATH]["post"].get(
        "responses"
    )

    for headers in ({}, {"Accept": "application/vnd.real-api+json; version=2027-01"}):
        if isinstance(application.application, litestar.Litestar):
            with LitestarTestClient(app=application.application) as test_client:
                response = test_client.post(TARGET_PATH, headers=headers)
            expected_status = status_codes.HTTP_201_CREATED
        else:
            with FastAPITestClient(app=application.application) as test_client:
                response = test_client.post(TARGET_PATH, headers=headers)
            expected_status = status_codes.HTTP_200_OK
        assert response.status_code == expected_status
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"status": "created"}


def build_security_schemes() -> dict[str, OpenApiSecurityScheme]:
    return {
        "httpAuth": OpenApiHttpSecurityScheme(scheme="bearer", bearer_format="JWT"),
        "apiKeyAuth": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
        "oauth": OpenApiOAuth2SecurityScheme(
            flows=OpenApiOAuthFlows(
                implicit=OpenApiOAuthFlow(authorization_url="/authorize", scopes={"read": "Read widgets"}),
                resource_owner=OpenApiOAuthFlow(token_url="/token", scopes={"write": "Write widgets"}),  # noqa: S106
                client_credentials=OpenApiOAuthFlow(token_url="/client-token", scopes={}),  # noqa: S106
                authorization_code=OpenApiOAuthFlow(
                    authorization_url="/code-authorize",
                    token_url="/code-token",  # noqa: S106
                    refresh_url="/refresh",
                    scopes={"admin": "Administer widgets"},
                ),
            )
        ),
        "oidc": OpenApiOpenIdConnectSecurityScheme(open_id_connect_url="/.well-known/openid-configuration"),
    }


def test_security_schemes_preserve_service_owned_schema_and_security(swagger_framework: str) -> None:
    security_schemes: typing.Final = build_security_schemes()
    baseline_application: typing.Final = build_application(swagger_framework, None)
    baseline_schema: typing.Final = baseline_application.schema()
    application: typing.Final = build_application(swagger_framework, None, security_schemes)
    schema: typing.Final = application.schema()

    assert schema["components"].get("schemas") == baseline_schema["components"].get("schemas")
    assert schema["components"]["securitySchemes"] == {
        **baseline_schema["components"]["securitySchemes"],
        **serialize_security_schemes(security_schemes),
    }
    assert schema.get("security") == baseline_schema.get("security")
    assert schema["paths"][TARGET_PATH]["get"].get("security") == baseline_schema["paths"][TARGET_PATH]["get"].get(
        "security"
    )
    assert application.schema() == schema


def test_security_schemes_combine_with_accept_version_documentation(swagger_framework: str) -> None:
    security_schemes: typing.Final = build_security_schemes()
    application: typing.Final = build_application(
        swagger_framework,
        build_version_docs_config(),
        security_schemes,
    )
    schema: typing.Final = application.schema()

    assert schema["components"]["securitySchemes"].items() >= serialize_security_schemes(security_schemes).items()
    assert schema["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == {
        "header": "Accept",
        "mediaType": "application/vnd.real-api+json",
        "parameter": "version",
        "supportedVersions": ["2026-01", "release-candidate"],
    }


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("conflicting_extension", "x-accept-versioning conflicts"),
        ("non_string_description", "has a non-string description"),
    ],
)
def test_fastapi_combined_openapi_augmentation_is_atomic_and_retryable(failure: str, error: str) -> None:
    service_schema: dict[str, typing.Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {
            TARGET_PATH: {
                "get": {"description": GET_DESCRIPTION},
                "post": {"description": POST_DESCRIPTION},
            }
        },
        "components": {"securitySchemes": {}},
    }
    failing_operation = service_schema["paths"][TARGET_PATH]["post"]
    if failure == "conflicting_extension":
        failing_operation["x-accept-versioning"] = {"header": "X-Service-Version"}
    else:
        failing_operation["description"] = 1
    baseline_schema: typing.Final = copy.deepcopy(service_schema)
    application: typing.Final = fastapi.FastAPI()
    application.openapi = lambda: service_schema  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
    instrument: typing.Final = FastApiSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=build_version_docs_config(),
        )
    )
    instrument.bootstrap_after(application)

    with pytest.raises(ValueError, match=error):
        application.openapi()

    assert service_schema == baseline_schema
    assert application.openapi_schema is None
    if failure == "conflicting_extension":
        failing_operation.pop("x-accept-versioning")
    else:
        failing_operation["description"] = POST_DESCRIPTION

    first_schema: typing.Final = application.openapi()
    second_schema: typing.Final = application.openapi()
    with FastAPITestClient(application) as client:
        served_schema: typing.Final = client.get("/openapi.json")

    assert first_schema is second_schema is service_schema
    assert first_schema["components"]["securitySchemes"]["serviceAuth"] == {"type": "http", "scheme": "bearer"}
    assert first_schema["paths"][TARGET_PATH]["get"]["x-accept-versioning"]["header"] == "Accept"
    assert served_schema.status_code == status_codes.HTTP_200_OK
    assert served_schema.json() == first_schema


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("conflicting_extension", "x-accept-versioning conflicts"),
        ("non_string_description", "has a non-string description"),
    ],
)
def test_litestar_combined_openapi_augmentation_is_atomic_and_retryable(failure: str, error: str) -> None:
    built_application: typing.Final = build_litestar_application(None)
    application: typing.Final = built_application.application
    assert isinstance(application, litestar.Litestar)
    assert application.openapi_schema is not None
    assert application.openapi_schema.paths is not None
    path_item: typing.Final = application.openapi_schema.paths[TARGET_PATH]
    assert isinstance(path_item, litestar_openapi.PathItem)
    assert path_item.get is not None
    assert path_item.post is not None
    original_get: typing.Final = path_item.get
    if failure == "conflicting_extension":
        path_item.post = add_accept_versioning_extension(path_item.post, {"header": "X-Service-Version"})
    else:
        path_item.post.description = 1  # type: ignore[assignment]  # Deliberately invalid service-owned schema.
    baseline_schema: typing.Final = copy.deepcopy(application.openapi_schema.to_schema())
    instrument: typing.Final = LitestarSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=build_version_docs_config(),
        )
    )

    with pytest.raises(ValueError, match=error):
        instrument.bootstrap_after(application)

    assert application.openapi_schema.to_schema() == baseline_schema
    assert path_item.get is original_get
    assert application.openapi_schema.components.security_schemes is not None
    assert "serviceAuth" not in application.openapi_schema.components.security_schemes
    if failure == "conflicting_extension":
        assert path_item.post is not None
        extension_field = next(
            field
            for field in dataclasses.fields(path_item.post)
            if field.metadata.get("alias") == "x-accept-versioning"
        )
        object.__setattr__(path_item.post, extension_field.name, None)
    else:
        path_item.post.description = POST_DESCRIPTION

    instrument.bootstrap_after(application)
    documented_get: typing.Final = path_item.get
    instrument.bootstrap_after(application)
    assert path_item.get is documented_get
    with LitestarTestClient(application) as client:
        first_served_schema: typing.Final = client.get("/schema/openapi.json")
        second_served_schema: typing.Final = client.get("/schema/openapi.json")

    assert application.openapi_schema.to_schema()["components"]["securitySchemes"]["serviceAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert first_served_schema.status_code == second_served_schema.status_code == status_codes.HTTP_200_OK
    assert first_served_schema.json() == second_served_schema.json() == application.openapi_schema.to_schema()


def test_fastapi_security_scheme_collisions_are_atomic_and_identical_schemes_are_retained() -> None:
    expected_scheme: typing.Final = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    service_schema: dict[str, typing.Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {"ServiceOwned": {"type": "object"}},
            "securitySchemes": {"matching": expected_scheme, "conflicting": {"type": "http", "scheme": "basic"}},
        },
    }
    application: typing.Final = fastapi.FastAPI()
    application.openapi = lambda: service_schema  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
    instrument: typing.Final = FastApiSwaggerInstrument(
        SwaggerConfig(
            security_schemes={
                "matching": OpenApiHttpSecurityScheme(scheme="bearer", bearer_format="JWT"),
            }
        )
    )
    instrument.bootstrap_after(application)

    assert application.openapi() is service_schema
    assert service_schema["components"] == {
        "schemas": {"ServiceOwned": {"type": "object"}},
        "securitySchemes": {"matching": expected_scheme, "conflicting": {"type": "http", "scheme": "basic"}},
    }

    with pytest.raises(ValueError, match="security scheme 'conflicting' conflicts"):
        add_fastapi_security_schemes(
            service_schema,
            {
                "insert": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
                "conflicting": OpenApiHttpSecurityScheme(scheme="bearer"),
            },
        )
    assert "insert" not in service_schema["components"]["securitySchemes"]


def test_litestar_security_scheme_collisions_are_atomic() -> None:
    application: typing.Final = build_litestar_application(None).application
    assert isinstance(application, litestar.Litestar)
    assert application.openapi_schema is not None
    assert application.openapi_schema.components.security_schemes is not None
    application.openapi_schema.components.security_schemes["conflicting"] = litestar_openapi.SecurityScheme(
        type="http",
        scheme="basic",
    )

    with pytest.raises(ValueError, match="security scheme 'conflicting' conflicts"):
        LitestarSwaggerInstrument(
            SwaggerConfig(
                security_schemes={
                    "insert": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
                    "conflicting": OpenApiHttpSecurityScheme(scheme="bearer"),
                }
            )
        ).bootstrap_after(application)
    assert "insert" not in application.openapi_schema.components.security_schemes


@pytest.mark.parametrize("settings_type", [FastApiSettings, LitestarSettings])
def test_openapi_settings_validate_security_schemes_and_operation_versions(
    settings_type: type[FastApiSettings] | type[LitestarSettings],
) -> None:
    settings: typing.Final = settings_type(
        security_schemes={"serviceBearer": {"type": "http", "scheme": "bearer"}},
        openapi_version_docs={
            "enabled": True,
            "vendor_media_type": "application/vnd.real-api+json",
            "supported_versions": ("2026-01",),
            "operation_versions": ({"path": TARGET_PATH, "method": "post", "supported_versions": ("2027-01",)},),
        },
    )

    assert settings.security_schemes == {"serviceBearer": OpenApiHttpSecurityScheme(scheme="bearer")}
    assert settings.openapi_version_docs is not None
    assert settings.openapi_version_docs.operation_versions == (
        OpenApiOperationVersionOverride(path=TARGET_PATH, method="post", supported_versions=("2027-01",)),
    )

    with pytest.raises(ValueError, match="must contain at least one"):
        OpenApiOperationVersionOverride(path=TARGET_PATH, method="post", supported_versions=())

    with pytest.raises(ValueError, match="duplicate path and method pairs"):
        OpenApiVersionDocsConfig(
            enabled=True,
            vendor_media_type="application/vnd.real-api+json",
            supported_versions=("2026-01",),
            operation_versions=(
                OpenApiOperationVersionOverride(path=TARGET_PATH, method="post", supported_versions=("2027-01",)),
                OpenApiOperationVersionOverride(path=TARGET_PATH, method="post", supported_versions=("2028-01",)),
            ),
        )


def test_fastapi_version_extension_conflict_is_not_overwritten() -> None:
    application: typing.Final = fastapi.FastAPI()
    application.openapi = lambda: {  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {
            TARGET_PATH: {
                "get": {
                    "description": GET_DESCRIPTION,
                    "x-accept-versioning": {"header": "X-Service-Version"},
                },
            },
        },
    }
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=build_version_docs_config())).bootstrap_after(
        application
    )

    with pytest.raises(ValueError, match="x-accept-versioning conflicts"):
        application.openapi()


def test_litestar_version_docs_preserve_service_owned_renderer_hooks_and_late_schema_cache() -> None:
    startup_hook: typing.Final = MagicMock()
    shutdown_hook: typing.Final = MagicMock()
    application: typing.Final = build_litestar_application(
        build_version_docs_config((OpenApiOperationSelector(path=TARGET_PATH, method="get"),)),
        startup_hook,
        shutdown_hook,
    )
    assert isinstance(application.application, litestar.Litestar)
    assert application.application.openapi_config is not None
    assert application.application.openapi_config.render_plugins[0] is application.renderer

    expected_schema: typing.Final = application.schema()
    with LitestarTestClient(app=application.application) as test_client:
        first_served_schema: typing.Final = test_client.get(application.schema_path)
        assert application.application.openapi_schema is not None
        assert application.application.openapi_schema.paths is not None
        target_path_item: typing.Final = application.application.openapi_schema.paths[TARGET_PATH]
        assert isinstance(target_path_item, litestar_openapi.PathItem)
        assert target_path_item.post is not None
        target_path_item.post.description = LATE_OPERATION_DESCRIPTION
        cached_schema: typing.Final = test_client.get(application.schema_path)

    assert first_served_schema.json() == expected_schema
    assert cached_schema.json() == expected_schema
    assert application.schema()["paths"][TARGET_PATH]["post"]["description"] == LATE_OPERATION_DESCRIPTION
    startup_hook.assert_called_once_with(application.application)
    shutdown_hook.assert_called_once_with(application.application)


def test_litestar_version_docs_preserve_custom_operation_subclasses_and_extensions() -> None:
    expected_extension: typing.Final[dict[str, str | list[str]]] = {
        "header": "Accept",
        "mediaType": "application/vnd.real-api+json",
        "parameter": "version",
        "supportedVersions": ["2026-01", "release-candidate"],
    }

    @dataclasses.dataclass(slots=True)
    class ServiceMetadataOperation(litestar_openapi.Operation):
        service_metadata: dict[str, str] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-service-metadata"},
        )
        rendering_state: str = dataclasses.field(init=False, default="draft")

        def service_owner(self) -> str | None:
            if self.service_metadata is None:
                return None
            return self.service_metadata["owner"]

        def to_schema(self) -> dict[str, typing.Any]:
            return {**super(ServiceMetadataOperation, self).to_schema(), "x-rendering-state": self.rendering_state}

    @dataclasses.dataclass(slots=True)
    class ServiceVersionedOperation(ServiceMetadataOperation):
        accept_versioning: dict[str, str | list[str]] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-accept-versioning"},
        )

    def custom_litestar_operation_generator(
        operation: litestar_openapi.Operation,
        accept_versioning: dict[str, str | list[str]] | None = None,
    ) -> ServiceMetadataOperation:
        operation_fields: typing.Final = {
            field.name: getattr(operation, field.name)
            for field in dataclasses.fields(operation)
            if field.name not in {"service_metadata", "accept_versioning", "rendering_state"}
        }
        if accept_versioning is None:
            return ServiceMetadataOperation(
                **operation_fields,
                service_metadata={"owner": "widgets"},
            )
        return ServiceVersionedOperation(
            **operation_fields,
            service_metadata={"owner": "widgets"},
            accept_versioning=accept_versioning,
        )

    @get(TARGET_PATH, description=GET_DESCRIPTION)
    async def list_service_widgets() -> dict[str, str]:
        return {"status": "ok"}

    application: typing.Final = litestar.Litestar(route_handlers=[list_service_widgets])
    assert application.openapi_schema is not None
    assert application.openapi_schema.paths is not None
    path_item: typing.Final = application.openapi_schema.paths[TARGET_PATH]
    assert isinstance(path_item, litestar_openapi.PathItem)
    assert path_item.get is not None
    service_owned_operation: typing.Final[ServiceVersionedOperation] = typing.cast(
        "ServiceVersionedOperation",
        custom_litestar_operation_generator(path_item.get, {}),
    )
    service_owned_operation.accept_versioning = None
    service_owned_operation.rendering_state = "published"
    path_item.get = service_owned_operation
    pre_adaptation_schema: typing.Final = service_owned_operation.to_schema()
    assert pre_adaptation_schema["x-service-metadata"] == {"owner": "widgets"}
    assert pre_adaptation_schema["x-rendering-state"] == "published"
    assert "x-accept-versioning" not in pre_adaptation_schema

    instrument: typing.Final = LitestarSwaggerInstrument(
        SwaggerConfig(openapi_version_docs=build_version_docs_config())
    )
    instrument.bootstrap_after(application)

    documented_operation: typing.Final = path_item.get
    assert type(documented_operation) is ServiceVersionedOperation
    assert documented_operation.service_owner() == "widgets"
    assert documented_operation.to_schema()["x-service-metadata"] == {"owner": "widgets"}
    assert documented_operation.to_schema()["x-rendering-state"] == "published"
    assert documented_operation.to_schema()["x-accept-versioning"] == expected_extension

    instrument.bootstrap_after(application)
    assert path_item.get is documented_operation
    assert documented_operation.rendering_state == "published"

    canonical_schema: typing.Final = application.openapi_schema.to_schema()
    with LitestarTestClient(app=application) as test_client:
        served_schema: typing.Final = test_client.get("/schema/openapi.json")

    assert canonical_schema["paths"][TARGET_PATH]["get"]["x-service-metadata"] == {"owner": "widgets"}
    assert canonical_schema["paths"][TARGET_PATH]["get"]["x-rendering-state"] == "published"
    assert canonical_schema["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == expected_extension
    assert served_schema.status_code == status_codes.HTTP_200_OK
    assert served_schema.json()["paths"][TARGET_PATH]["get"]["x-service-metadata"] == {"owner": "widgets"}
    assert served_schema.json()["paths"][TARGET_PATH]["get"]["x-rendering-state"] == "published"
    assert served_schema.json()["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == expected_extension

    matching_operation: typing.Final = custom_litestar_operation_generator(service_owned_operation, expected_extension)
    assert add_accept_versioning_extension(matching_operation, expected_extension) is matching_operation

    conflicting_operation: typing.Final = custom_litestar_operation_generator(
        service_owned_operation,
        {**expected_extension, "header": "X-Service-Version"},
    )
    with pytest.raises(ValueError, match="x-accept-versioning conflicts"):
        add_accept_versioning_extension(conflicting_operation, expected_extension)


def test_fastapi_production_version_docs_preserve_custom_generator_and_errors() -> None:
    application: typing.Final = fastapi.FastAPI()
    invocation_count = 0
    service_schema: typing.Final = {
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {
            TARGET_PATH: {
                "get": {
                    "description": GET_DESCRIPTION,
                    "responses": {"200": {"description": "OK"}},
                    "security": [{"ServiceAuth": []}],
                }
            }
        },
        "components": {
            "schemas": {"ServiceOwned": {"type": "object"}},
            "securitySchemes": {
                "GlobalAuth": {"type": "http", "scheme": "bearer"},
                "ServiceAuth": {"type": "http", "scheme": "bearer"},
            },
        },
        "security": [{"GlobalAuth": []}],
    }
    expected_schema: typing.Final = build_expected_documented_schema(service_schema, build_version_docs_config())

    def service_owned_openapi() -> dict[str, typing.Any]:
        nonlocal invocation_count
        invocation_count += 1
        return service_schema

    application.openapi = service_owned_openapi  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=build_version_docs_config())).bootstrap_after(
        application
    )

    first_schema: typing.Final = application.openapi()
    second_schema: typing.Final = application.openapi()

    assert invocation_count == EXPECTED_GENERATOR_CALLS
    assert first_schema is service_schema
    assert second_schema is service_schema
    assert first_schema == expected_schema
    assert first_schema["components"] == expected_schema["components"]
    assert first_schema["security"] == expected_schema["security"]
    assert first_schema["paths"][TARGET_PATH]["get"]["security"] == [{"ServiceAuth": []}]

    def failing_service_owned_openapi() -> dict[str, typing.Any]:
        raise RuntimeError("service-owned generator failed")

    failing_application: typing.Final = fastapi.FastAPI()
    failing_application.openapi = failing_service_owned_openapi  # type: ignore[method-assign]  # FastAPI's public hook.
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=build_version_docs_config())).bootstrap_after(
        failing_application
    )

    with pytest.raises(RuntimeError, match="service-owned generator failed"):
        failing_application.openapi()
