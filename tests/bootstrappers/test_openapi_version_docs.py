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
    OpenApiOperationVersionOverride,
    OpenApiSecurityScheme,
    OpenApiVersionDocsConfig,
    SwaggerConfig,
)
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper, FastApiSwaggerInstrument
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper, LitestarSwaggerInstrument
from microbootstrap.config.litestar import LitestarConfig
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
    framework: str
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
    security_schemes: dict[str, OpenApiSecurityScheme] | None = None,
    startup_hook: MagicMock | None = None,
    shutdown_hook: MagicMock | None = None,
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

        return BuiltApplication(framework, fastapi_application)

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
                on_startup=[startup_hook] if startup_hook is not None else [],
                on_shutdown=[shutdown_hook] if shutdown_hook is not None else [],
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
    return BuiltApplication(framework, litestar_application, renderer)


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

        FastApiSwaggerInstrument(SwaggerConfig(openapi_version_docs=configuration)).bootstrap_after(application)

        assert application.openapi() is schema
        assert schema["paths"][TARGET_PATH]["get"] is operation
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

    LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=configuration)).bootstrap_after(built.application)

    assert path_item.get is operation


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


def configured_schemes() -> dict[str, OpenApiSecurityScheme]:
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


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda operation: operation.update({"x-accept-versioning": {"header": "X-Service-Version"}}), "conflicts"),
        (lambda operation: operation.update({"description": 1}), "non-string description"),
    ],
)
def test_fastapi_preflight_is_atomic_and_retryable(
    mutation: typing.Callable[[dict[str, typing.Any]], None],
    error: str,
) -> None:
    application, schema = custom_fastapi_application()
    mutation(schema["paths"][TARGET_PATH]["post"])
    baseline = copy.deepcopy(schema)
    instrument = FastApiSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=version_docs(),
        )
    )
    instrument.bootstrap_after(application)

    with pytest.raises(ValueError, match=error):
        application.openapi()
    assert schema == baseline
    assert application.openapi_schema is None

    schema["paths"][TARGET_PATH]["post"] = {"description": "Create widget"}
    assert application.openapi() is schema
    assert schema["components"]["securitySchemes"]["serviceAuth"] == {"type": "http", "scheme": "bearer"}
    assert schema["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == EXTENSION


def test_fastapi_default_openapi_cache_retries_after_correcting_a_conflict() -> None:
    application = fastapi.FastAPI()

    @application.get(TARGET_PATH, openapi_extra={"x-accept-versioning": {"header": "X-Service-Version"}})
    async def list_widgets() -> dict[str, str]:
        return {"status": "ok"}

    FastApiSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=version_docs(),
        )
    ).bootstrap_after(application)

    with pytest.raises(ValueError, match="x-accept-versioning conflicts"):
        application.openapi()
    assert application.openapi_schema is not None
    application.openapi_schema["paths"][TARGET_PATH]["get"].pop("x-accept-versioning")

    corrected_schema = application.openapi()
    assert corrected_schema["components"]["securitySchemes"]["serviceAuth"] == {"type": "http", "scheme": "bearer"}
    assert corrected_schema["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == EXTENSION


def test_security_scheme_collisions_are_atomic_for_both_frameworks(framework: str) -> None:
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


def test_litestar_preserves_renderer_hooks_and_served_schema_cache() -> None:
    startup_hook = MagicMock()
    shutdown_hook = MagicMock()
    built = build_application("litestar", version_docs(), startup_hook=startup_hook, shutdown_hook=shutdown_hook)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_config is not None
    assert built.application.openapi_config.render_plugins[0] is built.renderer

    expected_schema = built.schema()
    with LitestarTestClient(app=built.application) as client:
        assert client.get("/schema/openapi.json").json() == expected_schema
        assert built.application.openapi_schema is not None
        assert built.application.openapi_schema.paths is not None
        built.application.openapi_schema.paths[TARGET_PATH].post.description = "Changed after serving"  # type: ignore[union-attr]
        assert client.get("/schema/openapi.json").json() == expected_schema
    assert built.schema()["paths"][TARGET_PATH]["post"]["description"] == "Changed after serving"
    startup_hook.assert_called_once_with(built.application)
    shutdown_hook.assert_called_once_with(built.application)


def test_litestar_standard_and_custom_operations_preserve_fields_and_state() -> None:
    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    assert built.application.openapi_schema.paths is not None
    path_item = built.application.openapi_schema.paths[TARGET_PATH]
    standard_operation = path_item.get
    assert standard_operation is not None
    standard_post = path_item.post
    assert standard_post is not None
    standard_fields = {
        field.name: getattr(standard_post, field.name)
        for field in dataclasses.fields(litestar_openapi.Operation)
        if field.name != "description"
    }
    original_fields = {
        field.name: getattr(standard_operation, field.name) for field in dataclasses.fields(standard_operation)
    }

    @dataclasses.dataclass
    class ServiceOperation(litestar_openapi.Operation):
        service_metadata: dict[str, str] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-service-metadata"},
        )
        accept_versioning: dict[str, str | list[str]] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-accept-versioning"},
        )
        state: str = dataclasses.field(init=False, default="draft")

    custom_operation = ServiceOperation(**original_fields, service_metadata={"owner": "widgets"})
    custom_operation.state = "published"
    path_item.get = custom_operation
    instrument = LitestarSwaggerInstrument(SwaggerConfig(openapi_version_docs=version_docs()))
    instrument.bootstrap_after(built.application)

    documented = path_item.get
    assert documented is not standard_operation
    assert type(documented) is ServiceOperation
    assert documented.service_metadata == {"owner": "widgets"}
    assert documented.state == "published"
    assert documented.accept_versioning == EXTENSION
    assert all(getattr(path_item.post, name) == value for name, value in standard_fields.items())
    assert type(path_item.post).__name__ == "AcceptVersionedOperation"
    assert built.schema()["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == EXTENSION
    assert built.served_schema()["paths"][TARGET_PATH]["get"]["x-accept-versioning"] == EXTENSION
    documented_post = path_item.post
    instrument.bootstrap_after(built.application)
    assert path_item.get is documented
    assert path_item.post is documented_post


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("conflicting_extension", "x-accept-versioning conflicts"),
        ("non_string_description", "non-string description"),
    ],
)
def test_litestar_aliased_operation_preflight_is_atomic_and_retryable(failure: str, error: str) -> None:
    built = build_application("litestar", None)
    assert isinstance(built.application, litestar.Litestar)
    assert built.application.openapi_schema is not None
    assert built.application.openapi_schema.paths is not None
    path_item = built.application.openapi_schema.paths[TARGET_PATH]
    assert path_item.get is not None
    assert path_item.post is not None

    @dataclasses.dataclass
    class AliasedOperation(litestar_openapi.Operation):
        accept_versioning: dict[str, str | list[str]] | None = dataclasses.field(
            default=None,
            metadata={"alias": "x-accept-versioning"},
        )

    fields = {field.name: getattr(path_item.post, field.name) for field in dataclasses.fields(path_item.post)}
    custom_operation = AliasedOperation(**fields)
    if failure == "conflicting_extension":
        custom_operation.accept_versioning = {"header": "X-Service-Version"}
    else:
        custom_operation.description = 1  # type: ignore[assignment]  # Deliberately invalid service-owned schema.
    path_item.post = custom_operation
    original_get = path_item.get
    baseline = copy.deepcopy(built.application.openapi_schema.to_schema())
    instrument = LitestarSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=version_docs(),
        )
    )

    with pytest.raises(ValueError, match=error):
        instrument.bootstrap_after(built.application)

    assert built.application.openapi_schema.to_schema() == baseline
    assert path_item.get is original_get
    assert path_item.post is custom_operation
    assert built.application.openapi_schema.components.security_schemes is not None
    assert "serviceAuth" not in built.application.openapi_schema.components.security_schemes

    if failure == "conflicting_extension":
        custom_operation.accept_versioning = None
    else:
        custom_operation.description = "Create widget"
    instrument.bootstrap_after(built.application)
    documented_post = path_item.post
    instrument.bootstrap_after(built.application)

    assert path_item.post is documented_post
    assert built.application.openapi_schema.to_schema()["components"]["securitySchemes"]["serviceAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert (
        built.application.openapi_schema.to_schema()["paths"][TARGET_PATH]["post"]["x-accept-versioning"] == EXTENSION
    )


def test_litestar_rejects_unsupported_custom_operation_without_partial_updates() -> None:
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
    baseline = copy.deepcopy(built.schema())
    with pytest.raises(TypeError, match="must declare an x-accept-versioning alias"):
        LitestarSwaggerInstrument(
            SwaggerConfig(
                security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
                openapi_version_docs=version_docs(),
            )
        ).bootstrap_after(built.application)
    assert built.schema() == baseline
    assert built.application.openapi_schema.components.security_schemes is not None
    assert "serviceAuth" not in built.application.openapi_schema.components.security_schemes
    path_item.post = path_item.get
    LitestarSwaggerInstrument(
        SwaggerConfig(
            security_schemes={"serviceAuth": OpenApiHttpSecurityScheme(scheme="bearer")},
            openapi_version_docs=version_docs(),
        )
    ).bootstrap_after(built.application)
    assert "serviceAuth" in built.application.openapi_schema.components.security_schemes


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
