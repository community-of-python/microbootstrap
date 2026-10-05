import copy
import dataclasses
import typing

import fastapi
import litestar
import pytest
from fastapi.security import HTTPBearer
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import get, openapi, post, status_codes
from litestar.config.app import AppConfig
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
    OpenApiOperationVersionOverride,
    OpenApiVersionDocsConfig,
    SwaggerConfig,
)
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper, FastApiSwaggerInstrument
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper, LitestarSwaggerInstrument
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.openapi_security_schemes import _OpenApiSecurityScheme
from microbootstrap.settings import FastApiSettings, LitestarSettings


TARGET_PATH: typing.Final = "/widgets"
HEALTH_PATH: typing.Final = "/service-health"
NO_DESCRIPTION_PATH: typing.Final = "/without-description"
EXTENSION: typing.Final = {
    "header": "Accept",
    "mediaType": "application/vnd.real-api+json",
    "parameter": "version",
    "supportedVersions": ["2026-01", "release-candidate"],
}
VERSION_TEXT: typing.Final = (
    "Supported API versions:\n"
    "- `application/vnd.real-api+json; version=2026-01`.\n"
    "- `application/vnd.real-api+json; version=release-candidate`."
)
EXPECTED_GENERATOR_CALLS: typing.Final = 2
VERSIONED_OPERATIONS: typing.Final = (
    (TARGET_PATH, "get"),
    (TARGET_PATH, "post"),
    (HEALTH_PATH, "get"),
    (NO_DESCRIPTION_PATH, "get"),
)


class ServiceResponse(BaseModel):
    status: str


@dataclasses.dataclass
class BuiltApplication:
    application: fastapi.FastAPI | litestar.Litestar
    renderer: SwaggerRenderPlugin | None = None

    def schema(self) -> dict[str, typing.Any]:
        if isinstance(self.application, litestar.Litestar):
            assert self.application.openapi_schema is not None
            return self.application.openapi_schema.to_schema()
        return self.application.openapi()

    def served_schema(self) -> dict[str, typing.Any]:
        if isinstance(self.application, litestar.Litestar):
            with LitestarTestClient(app=self.application) as client:
                response = client.get("/schema/openapi.json")
        else:
            with FastAPITestClient(app=self.application) as client:
                response = client.get("/openapi.json")
        assert response.status_code == status_codes.HTTP_200_OK
        return typing.cast("dict[str, typing.Any]", response.json())

    def create_widget(self, headers: dict[str, str] | None = None) -> None:
        if isinstance(self.application, litestar.Litestar):
            with LitestarTestClient(app=self.application) as client:
                response = client.post(TARGET_PATH, headers=headers)
            expected_status = status_codes.HTTP_201_CREATED
        else:
            with FastAPITestClient(app=self.application) as client:
                response = client.post(TARGET_PATH, headers=headers)
            expected_status = status_codes.HTTP_200_OK
        assert response.status_code == expected_status
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"status": "created"}


@pytest.fixture(params=("fastapi", "litestar"))
def framework(request: pytest.FixtureRequest) -> str:
    return typing.cast("str", request.param)


def version_docs(
    *,
    overrides: tuple[OpenApiOperationVersionOverride, ...] = (),
) -> OpenApiVersionDocsConfig:
    return OpenApiVersionDocsConfig(
        vendor_media_type="application/vnd.real-api+json",
        supported_versions=("2026-01", "release-candidate"),
        operation_versions=overrides,
    )


def build_application(
    framework: str,
    config: OpenApiVersionDocsConfig | None,
    security_schemes: dict[str, _OpenApiSecurityScheme] | None = None,
) -> BuiltApplication:
    if framework == "fastapi":
        fastapi_application = FastApiBootstrapper(
            FastApiSettings(
                service_debug=False,
                security_schemes=security_schemes or {},
                openapi_version_docs=config,
            )
        ).bootstrap()
        service_auth = HTTPBearer()

        @fastapi_application.get(TARGET_PATH, description="List widgets", dependencies=[fastapi.Security(service_auth)])
        async def fastapi_list_widgets() -> dict[str, str]:
            return {"status": "ok"}

        @fastapi_application.post(TARGET_PATH, description="Create widget")
        async def fastapi_create_widget() -> dict[str, str]:
            return {"status": "created"}

        @fastapi_application.get(HEALTH_PATH, description="Service health")
        async def fastapi_service_health() -> dict[str, str]:
            return {"status": "ok"}

        @fastapi_application.get(NO_DESCRIPTION_PATH)
        async def fastapi_without_description() -> dict[str, str]:
            return {"status": "ok"}

        return BuiltApplication(fastapi_application)

    @get(TARGET_PATH, description="List widgets", security=[{"ServiceAuth": []}])
    async def litestar_list_widgets() -> ServiceResponse:
        return ServiceResponse(status="ok")

    @post(TARGET_PATH, description="Create widget")
    async def litestar_create_widget() -> ServiceResponse:
        return ServiceResponse(status="created")

    @get(HEALTH_PATH, description="Service health")
    async def litestar_service_health() -> dict[str, str]:
        return {"status": "ok"}

    @get(NO_DESCRIPTION_PATH)
    async def litestar_without_description() -> dict[str, str]:
        return {"status": "ok"}

    renderer = SwaggerRenderPlugin()
    litestar_application = (
        LitestarBootstrapper(
            LitestarSettings(
                service_debug=False,
                security_schemes=security_schemes or {},
                openapi_version_docs=config,
            )
        )
        .configure_application(
            LitestarConfig(
                route_handlers=[
                    litestar_list_widgets,
                    litestar_create_widget,
                    litestar_service_health,
                    litestar_without_description,
                ],
                openapi_config=openapi.OpenAPIConfig(
                    title="Service API",
                    version="1.0.0",
                    components=litestar_openapi.Components(
                        security_schemes={
                            "GlobalAuth": litestar_openapi.SecurityScheme(type="http", scheme="bearer"),
                            "ServiceAuth": litestar_openapi.SecurityScheme(type="http", scheme="bearer"),
                        }
                    ),
                    security=[{"GlobalAuth": []}],
                    render_plugins=[renderer],
                ),
            )
        )
        .bootstrap()
    )
    return BuiltApplication(litestar_application, renderer)


def test_version_docs_change_only_selected_operations_and_match_served_schema(framework: str) -> None:
    baseline = build_application(framework, None).schema()
    application = build_application(
        framework,
        version_docs(
            overrides=(OpenApiOperationVersionOverride(path=TARGET_PATH, method="get", supported_versions=()),),
        ),
    )

    schema = application.schema()
    comparable_schema = copy.deepcopy(schema)
    comparable_baseline = copy.deepcopy(baseline)
    for path, method in ((TARGET_PATH, "post"), (HEALTH_PATH, "get"), (NO_DESCRIPTION_PATH, "get")):
        comparable_schema["paths"][path][method].pop("description")
        comparable_schema["paths"][path][method].pop("x-accept-versioning")
        comparable_baseline["paths"][path][method].pop("description", None)

    assert application.schema() == schema
    assert application.served_schema() == schema
    assert comparable_schema == comparable_baseline
    assert schema["components"] == baseline["components"]
    assert schema.get("security") == baseline.get("security")
    assert schema["paths"][TARGET_PATH]["get"] == baseline["paths"][TARGET_PATH]["get"]
    assert schema["paths"][TARGET_PATH]["post"]["description"] == f"Create widget\n\n{VERSION_TEXT}"
    assert schema["paths"][HEALTH_PATH]["get"]["description"] == f"Service health\n\n{VERSION_TEXT}"
    assert schema["paths"][NO_DESCRIPTION_PATH]["get"]["description"] == VERSION_TEXT
    assert schema["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == EXTENSION
    application.create_widget()


def test_absent_version_docs_leave_schema_and_runtime_unchanged(
    framework: str,
) -> None:
    baseline = build_application(framework, None)
    application = build_application(framework, None)

    assert application.schema() == baseline.schema()
    assert application.served_schema() == baseline.schema()
    application.create_widget()


def test_empty_operation_override_skips_malformed_service_owned_metadata(framework: str) -> None:
    configuration = version_docs(
        overrides=(OpenApiOperationVersionOverride(path=TARGET_PATH, method="get", supported_versions=()),),
    )
    if framework == "fastapi":
        application, schema = custom_fastapi_application()
        operation = schema["paths"][TARGET_PATH]["get"]
        operation.update({"description": 1, "x-accept-versioning": {"header": "X-Service-Version"}})
        snapshot = copy.deepcopy(operation)

        FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=configuration)).bootstrap_after(application)

        assert application.openapi() is schema
        assert schema["paths"][TARGET_PATH]["get"] is operation
        assert operation == snapshot
        return

    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    assert built.application.openapi_schema.paths is not None
    path_item = built.application.openapi_schema.paths[TARGET_PATH]
    assert path_item.get is not None

    @dataclasses.dataclass
    class ServiceOperation(litestar_openapi.Operation):
        accept_versioning: dict[str, str | list[str]] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-accept-versioning"},
        )

    fields = {field.name: getattr(path_item.get, field.name) for field in dataclasses.fields(path_item.get)}
    operation = ServiceOperation(**fields, accept_versioning={"header": "X-Service-Version"})
    operation.description = 1  # type: ignore[assignment]  # Deliberately invalid service-owned schema.
    path_item.get = operation
    snapshot = copy.deepcopy(operation)

    LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=configuration)).bootstrap_after(built.application)

    assert path_item.get is operation
    assert operation == snapshot


def test_version_docs_do_not_create_absent_security_scheme_containers(framework: str) -> None:
    if framework == "fastapi":
        application, schema = custom_fastapi_application()
        schema.pop("components")
        FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(application)

        assert application.openapi() is schema
        assert "components" not in schema
        return

    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    built.application.openapi_schema.components.security_schemes = None
    LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(built.application)

    assert built.application.openapi_schema.components.security_schemes is None


@pytest.mark.parametrize(
    ("configuration", "expected_description", "expected_extension"),
    [
        (
            OpenApiVersionDocsConfig(
                vendor_media_type="application/vnd.real-api+json",
                supported_versions=("2027-01",),
            ),
            "Create widget\n\nSupported API version: `application/vnd.real-api+json; version=2027-01`.",
            {
                "header": "Accept",
                "mediaType": "application/vnd.real-api+json",
                "parameter": "version",
                "supportedVersions": ["2027-01"],
            },
        ),
        (
            version_docs(
                overrides=(
                    OpenApiOperationVersionOverride(
                        path=TARGET_PATH,
                        method="post",
                        supported_versions=("2027-01",),
                    ),
                )
            ),
            "Create widget\n\nSupported API version: `application/vnd.real-api+json; version=2027-01`.",
            {
                "header": "Accept",
                "mediaType": "application/vnd.real-api+json",
                "parameter": "version",
                "supportedVersions": ["2027-01"],
            },
        ),
    ],
)
def test_single_global_or_operation_override_version_and_accept_header_do_not_change_runtime(
    framework: str,
    configuration: OpenApiVersionDocsConfig,
    expected_description: str,
    expected_extension: dict[str, str | list[str]],
) -> None:
    baseline = build_application(framework, None).schema()
    application = build_application(
        framework,
        configuration,
    )

    operation = application.schema()["paths"][TARGET_PATH]["post"]
    assert operation["description"] == expected_description
    assert operation["x-accept-versioning"] == expected_extension
    assert operation.get("parameters") == baseline["paths"][TARGET_PATH]["post"].get("parameters")
    assert operation.get("responses") == baseline["paths"][TARGET_PATH]["post"].get("responses")
    application.create_widget()
    application.create_widget({"Accept": "application/vnd.real-api+json; version=2027-01"})


def configured_schemes() -> dict[str, _OpenApiSecurityScheme]:
    return {
        "httpAuth": OpenApiHttpSecurityScheme(scheme="bearer", bearer_format="JWT"),
        "apiKeyAuth": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
        "oauth": OpenApiOAuth2SecurityScheme(
            flows=OpenApiOAuthFlows(
                implicit=OpenApiOAuthFlow(
                    authorization_url="/implicit-authorize",
                    refresh_url="/implicit-refresh",
                    scopes={"read": "Read widgets"},
                ),
                resource_owner=OpenApiOAuthFlow(
                    token_url="/password-token",  # noqa: S106
                    refresh_url="/password-refresh",
                    scopes={"write": "Write widgets"},
                ),
                client_credentials=OpenApiOAuthFlow(
                    token_url="/client-token",  # noqa: S106
                    refresh_url="/client-refresh",
                    scopes={"service": "Service access"},
                ),
                authorization_code=OpenApiOAuthFlow(
                    authorization_url="/code-authorize",
                    token_url="/code-token",  # noqa: S106
                    refresh_url="/code-refresh",
                    scopes={"admin": "Administer widgets"},
                ),
            )
        ),
        "oidc": OpenApiOpenIdConnectSecurityScheme(open_id_connect_url="/.well-known/openid-configuration"),
    }


def test_security_schemes_preserve_service_owned_security_and_combine_with_version_docs(framework: str) -> None:
    schemes = configured_schemes()
    baseline = build_application(framework, None).schema()
    application = build_application(framework, version_docs(), schemes)

    schema = application.schema()
    comparable_schema = copy.deepcopy(schema)
    for scheme_name in schemes:
        comparable_schema["components"]["securitySchemes"].pop(scheme_name)
    for path, method in VERSIONED_OPERATIONS:
        comparable_schema["paths"][path][method].pop("description")
        comparable_schema["paths"][path][method].pop("x-accept-versioning")
    comparable_baseline = copy.deepcopy(baseline)
    for path, method in VERSIONED_OPERATIONS:
        comparable_baseline["paths"][path][method].pop("description", None)

    assert comparable_schema == comparable_baseline
    assert schema["components"]["securitySchemes"] == {
        **(
            {"HTTPBearer": {"type": "http", "scheme": "bearer"}}
            if framework == "fastapi"
            else {
                "GlobalAuth": {"type": "http", "scheme": "bearer"},
                "ServiceAuth": {"type": "http", "scheme": "bearer"},
            }
        ),
        "httpAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "apiKeyAuth": {"type": "apiKey", "name": "X-API-Key", "in": "header"},
        "oauth": {
            "type": "oauth2",
            "flows": {
                "implicit": {
                    "authorizationUrl": "/implicit-authorize",
                    "refreshUrl": "/implicit-refresh",
                    "scopes": {"read": "Read widgets"},
                },
                "password": {
                    "tokenUrl": "/password-token",
                    "refreshUrl": "/password-refresh",
                    "scopes": {"write": "Write widgets"},
                },
                "clientCredentials": {
                    "tokenUrl": "/client-token",
                    "refreshUrl": "/client-refresh",
                    "scopes": {"service": "Service access"},
                },
                "authorizationCode": {
                    "authorizationUrl": "/code-authorize",
                    "tokenUrl": "/code-token",
                    "refreshUrl": "/code-refresh",
                    "scopes": {"admin": "Administer widgets"},
                },
            },
        },
        "oidc": {"type": "openIdConnect", "openIdConnectUrl": "/.well-known/openid-configuration"},
    }
    assert schema.get("security") == baseline.get("security")
    assert schema["paths"][TARGET_PATH]["get"].get("security") == baseline["paths"][TARGET_PATH]["get"].get("security")
    assert schema["paths"][TARGET_PATH]["post"]["description"] == f"Create widget\n\n{VERSION_TEXT}"
    assert schema["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == EXTENSION
    assert application.served_schema() == schema


def custom_fastapi_application() -> tuple[fastapi.FastAPI, dict[str, typing.Any]]:
    schema: dict[str, typing.Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {TARGET_PATH: {"get": {"description": "List widgets"}, "post": {"description": "Create widget"}}},
        "components": {"securitySchemes": {}},
    }
    application = fastapi.FastAPI()
    application.openapi = lambda: schema  # type: ignore[method-assign]  # Public custom OpenAPI hook.
    return application, schema


def test_security_scheme_conflicts_leave_the_definition_batch_unchanged(framework: str) -> None:
    if framework == "fastapi":
        application, schema = custom_fastapi_application()
        schema["components"]["securitySchemes"] = {
            "matching": {"type": "http", "scheme": "bearer"},
            "conflict": {"type": "http", "scheme": "basic"},
        }
        FastApiSwaggerInstrument(
            SwaggerConfig(security_schemes={"matching": OpenApiHttpSecurityScheme(scheme="bearer")})
        ).bootstrap_after(application)
        assert application.openapi() is schema
        instrument = FastApiSwaggerInstrument(
            SwaggerConfig(
                security_schemes={
                    "insert": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
                    "conflict": OpenApiHttpSecurityScheme(scheme="bearer"),
                }
            )
        )
        instrument.bootstrap_after(application)
        with pytest.raises(ValueError, match="security scheme 'conflict' conflicts"):
            application.openapi()
        assert "insert" not in schema["components"]["securitySchemes"]
        return

    litestar_application = build_application("litestar", None).application
    assert isinstance(litestar_application, litestar.Litestar)
    assert litestar_application.openapi_schema is not None
    assert litestar_application.openapi_schema.components.security_schemes is not None
    matching_scheme = litestar_openapi.SecurityScheme(type="http", scheme="bearer")
    litestar_application.openapi_schema.components.security_schemes["matching"] = matching_scheme
    LitestarSwaggerInstrument(
        SwaggerConfig(security_schemes={"matching": OpenApiHttpSecurityScheme(scheme="bearer")})
    ).bootstrap_after(litestar_application)
    assert litestar_application.openapi_schema.components.security_schemes["matching"] is matching_scheme
    litestar_application.openapi_schema.components.security_schemes["conflict"] = litestar_openapi.SecurityScheme(
        type="http",
        scheme="basic",
    )
    with pytest.raises(ValueError, match="security scheme 'conflict' conflicts"):
        LitestarSwaggerInstrument(
            SwaggerConfig(
                security_schemes={
                    "insert": OpenApiApiKeySecurityScheme(name="X-API-Key", location="header"),
                    "conflict": OpenApiHttpSecurityScheme(scheme="bearer"),
                }
            )
        ).bootstrap_after(litestar_application)
    assert "insert" not in litestar_application.openapi_schema.components.security_schemes


def test_fastapi_preserves_custom_generator_calls_and_errors() -> None:
    application, schema = custom_fastapi_application()
    calls = 0

    def generator() -> dict[str, typing.Any]:
        nonlocal calls
        calls += 1
        return schema

    application.openapi = generator  # type: ignore[method-assign]  # Public custom OpenAPI hook.
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(application)
    assert application.openapi() is schema
    assert application.openapi() is schema
    assert calls == EXPECTED_GENERATOR_CALLS

    failing_application = fastapi.FastAPI()
    failing_application.openapi = lambda: (_ for _ in ()).throw(RuntimeError("service-owned generator failed"))  # type: ignore[method-assign]
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(failing_application)
    with pytest.raises(RuntimeError, match="service-owned generator failed"):
        failing_application.openapi()


def test_fastapi_documents_http_operations_without_altering_path_item_metadata() -> None:
    application = fastapi.FastAPI()
    schema: dict[str, typing.Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Service API", "version": "1.0.0"},
        "paths": {
            TARGET_PATH: {
                "summary": "Widgets",
                "parameters": [{"$ref": "#/components/parameters/RequestedBy"}],
                "servers": [{"url": "https://widgets.example.test"}],
                "x-service-metadata": {"owner": "widgets"},
                "get": {"description": "List widgets", "responses": {"200": {"description": "OK"}}},
            }
        },
        "components": {
            "parameters": {"RequestedBy": {"name": "X-Requested-By", "in": "header", "schema": {"type": "string"}}}
        },
    }
    application.openapi = lambda: schema  # type: ignore[method-assign]  # Public custom OpenAPI hook.
    FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(application)

    canonical_schema = application.openapi()
    repeated_schema = application.openapi()
    with FastAPITestClient(app=application) as client:
        served_schema = client.get("/openapi.json")

    assert served_schema.status_code == status_codes.HTTP_200_OK
    assert canonical_schema is schema
    assert repeated_schema is schema
    assert served_schema.json() == schema
    assert schema["paths"][TARGET_PATH] == {
        "summary": "Widgets",
        "parameters": [{"$ref": "#/components/parameters/RequestedBy"}],
        "servers": [{"url": "https://widgets.example.test"}],
        "x-service-metadata": {"owner": "widgets"},
        "get": {
            "description": f"List widgets\n\n{VERSION_TEXT}",
            "responses": {"200": {"description": "OK"}},
            "x-accept-versioning": EXTENSION,
        },
    }


def test_litestar_served_schema_matches_canonical_schema_on_repeated_reads() -> None:
    built = build_application("litestar", version_docs())
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_config is not None
    assert built.application.openapi_config.render_plugins[0] is built.renderer

    expected_schema = built.schema()
    assert built.served_schema() == expected_schema
    assert built.served_schema() == expected_schema


@pytest.mark.parametrize(
    ("has_security_schemes", "has_version_docs"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_litestar_bootstraps_without_openapi_config(
    has_security_schemes: bool,
    has_version_docs: bool,
) -> None:
    @get(TARGET_PATH)
    async def handler() -> dict[str, str]:
        return {"status": "ok"}

    def disable_openapi(configuration: AppConfig) -> AppConfig:
        configuration.openapi_config = None
        return configuration

    application = (
        LitestarBootstrapper(
            LitestarSettings(
                service_debug=False,
                security_schemes={"ServiceAuth": OpenApiHttpSecurityScheme(scheme="bearer")}
                if has_security_schemes
                else {},
                openapi_version_docs=version_docs() if has_version_docs else None,
            )
        )
        .configure_application(LitestarConfig(route_handlers=[handler], on_app_init=[disable_openapi]))
        .bootstrap()
    )

    assert application.openapi_config is None
    with LitestarTestClient(app=application) as client:
        response = client.get(TARGET_PATH)
        openapi_response = client.get("/docs/openapi.json")
    assert response.status_code == status_codes.HTTP_200_OK
    assert response.json() == {"status": "ok"}
    assert openapi_response.status_code == status_codes.HTTP_404_NOT_FOUND


def test_litestar_standard_operations_preserve_fields_and_are_stable() -> None:
    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    assert built.application.openapi_schema.paths is not None
    path_item = built.application.openapi_schema.paths[TARGET_PATH]
    standard_post = path_item.post
    assert standard_post is not None
    standard_fields = {
        field.name: getattr(standard_post, field.name)
        for field in dataclasses.fields(litestar_openapi.Operation)
        if field.name != "description"
    }
    instrument = LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs()))
    instrument.bootstrap_after(built.application)

    assert all(getattr(path_item.post, name) == value for name, value in standard_fields.items())
    assert built.schema()["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == EXTENSION
    assert built.served_schema()["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == EXTENSION
    documented_post = path_item.post
    instrument.bootstrap_after(built.application)
    assert path_item.post is documented_post


def test_litestar_rejects_unsupported_custom_operation() -> None:
    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    assert built.application.openapi_schema.paths is not None
    path_item = built.application.openapi_schema.paths[TARGET_PATH]
    assert path_item.post is not None

    @dataclasses.dataclass
    class UnsupportedOperation(litestar_openapi.Operation):
        metadata: dict[str, str] | None = dataclasses.field(default=None, metadata={"alias": "x-service-metadata"})

    fields = {field.name: getattr(path_item.post, field.name) for field in dataclasses.fields(path_item.post)}
    path_item.post = UnsupportedOperation(**fields, metadata={"owner": "widgets"})
    with pytest.raises(TypeError, match="is not supported for Accept version documentation"):
        LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs())).bootstrap_after(built.application)
