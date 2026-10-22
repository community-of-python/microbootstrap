import copy
import http
import typing

import litestar
import pydantic
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.openapi import spec
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap import FastApiSettings, LitestarSettings
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.health_checks_instrument import HealthCheckTypedDict


class Payload(pydantic.BaseModel):
    value: pydantic.JsonValue


def test_fastapi_descriptions_preserve_validation_and_are_idempotent() -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(api_metadata_enabled=True, service_debug=False, health_checks_enabled=False)
    ).bootstrap()

    @application.post("/items")
    def create_item(payload: Payload) -> Payload:
        return payload

    before: typing.Final = copy.deepcopy(application.openapi())
    after: typing.Final = copy.deepcopy(application.openapi())
    assert application.openapi() == after
    assert "security" not in after
    schemas: typing.Final = after["components"]["schemas"]
    assert schemas["JsonValue"]["description"].startswith("JSON value:")
    assert schemas["HTTPValidationError"]["properties"]["detail"]["description"]
    assert schemas["ValidationError"]["properties"]["loc"]["description"]
    for name in ("HTTPValidationError", "ValidationError"):
        assert schemas[name].get("required") == before["components"]["schemas"][name].get("required")
        assert set(schemas[name]["properties"]) == set(before["components"]["schemas"][name]["properties"])
    with FastAPITestClient(application) as client:
        assert client.post("/items", json={"value": {"nested": [1, None]}}).json() == {"value": {"nested": [1, None]}}
        rejected = client.post("/items", json={})
    assert rejected.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert set(rejected.json()) == {"detail", "title"}
    assert schemas["HTTPValidationError"]["properties"]["title"]["description"]


def test_fastapi_empty_schema_is_supported() -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(api_metadata_enabled=True, service_debug=False, health_checks_enabled=False)
    ).bootstrap()
    assert "security" not in application.openapi()
    assert not application.openapi().get("components", {}).get("schemas")


def test_litestar_metadata_describes_schemas_and_preserves_successful_responses() -> None:
    @litestar.get("/example-health", sync_to_thread=False)
    def get_health() -> HealthCheckTypedDict:
        return {"health_status": True}

    @litestar.get("/items/{item_id:int}", sync_to_thread=False)
    def get_item(item_id: int, limit: int = 1) -> int:
        return item_id * limit

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(api_metadata_enabled=True, service_debug=False))
        .configure_application(LitestarConfig(route_handlers=[get_health, get_item]))
        .bootstrap()
    )
    document: typing.Final = application.openapi_schema
    before: typing.Final = copy.deepcopy(document.to_schema())
    LitestarBootstrapper(LitestarSettings(api_metadata_enabled=True, service_debug=False)).bootstrap_after(application)
    after: typing.Final = copy.deepcopy(document.to_schema())
    LitestarBootstrapper(LitestarSettings(api_metadata_enabled=True, service_debug=False)).bootstrap_after(application)
    assert document.to_schema() == after
    health: typing.Final = after["components"]["schemas"]["HealthCheckTypedDict"]
    assert health["properties"]["health_status"]["description"].startswith("Static process health")
    error: typing.Final = after["paths"]["/items/{item_id}"]["get"]["responses"]["400"]["content"]["application/json"][
        "schema"
    ]
    assert error["properties"]["detail"]["description"]
    assert error["properties"]["title"]["description"]
    before_error: typing.Final = before["paths"]["/items/{item_id}"]["get"]["responses"]["400"]["content"][
        "application/json"
    ]["schema"]
    assert error["required"] == before_error["required"]
    assert set(error["properties"]) == set(before_error["properties"])
    item_id: typing.Final = 42
    with LitestarTestClient(application) as client:
        assert client.get("/example-health").json() == {"health_status": True}
        assert client.get(f"/items/{item_id}").json() == item_id
        rejected = client.get(f"/items/{item_id}?limit=invalid")
    assert rejected.status_code == http.HTTPStatus.BAD_REQUEST
    assert set(rejected.json()) == {"status_code", "detail", "extra", "title"}


def test_composite_error_schemas_and_references_keep_their_shapes() -> None:
    detail: typing.Final = spec.Schema(type=spec.OpenAPIType.STRING)
    owned: typing.Final = spec.Schema(description="Owned detail")
    branch: typing.Final = spec.Schema(type=spec.OpenAPIType.OBJECT, properties={"detail": detail})
    compound: typing.Final = spec.Schema(
        one_of=[branch, spec.Schema(type=spec.OpenAPIType.OBJECT)],
        any_of=[spec.Schema(properties={"detail": owned})],
        all_of=[spec.Reference(ref="#/components/schemas/Other")],
    )
    mixed: typing.Final = spec.Schema(
        one_of=[spec.Reference(ref="#/components/schemas/Other"), spec.Schema(type=spec.OpenAPIType.STRING)]
    )
    success: typing.Final = spec.Schema(properties={"detail": spec.Schema()})
    operation: typing.Final = spec.Operation(
        responses={
            "200": spec.OpenAPIResponse(
                description="OK", content={"application/json": spec.OpenAPIMediaType(schema=success)}
            ),
            "400": spec.OpenAPIResponse(
                description="Bad request", content={"application/json": spec.OpenAPIMediaType(schema=compound)}
            ),
            "401": spec.OpenAPIResponse(
                description="Unauthorized", content={"application/json": spec.OpenAPIMediaType(schema=mixed)}
            ),
            "402": spec.Reference(ref="#/components/responses/Payment"),
            "403": spec.OpenAPIResponse(
                description="Forbidden",
                content={
                    "application/json": spec.OpenAPIMediaType(
                        schema=spec.Reference(ref="#/components/schemas/Forbidden")
                    )
                },
            ),
            "500": spec.OpenAPIResponse(description="Internal error"),
        }
    )
    application: typing.Final = litestar.Litestar(route_handlers=[])
    document: typing.Final = application.openapi_schema
    document.paths = {"/items": spec.PathItem(get=operation)}
    document.components.schemas = {"JsonValue": spec.Schema(description="Owned JSON description")}
    LitestarBootstrapper(LitestarSettings(api_metadata_enabled=True, service_debug=False)).bootstrap_after(application)
    assert document.components.schemas["JsonValue"].description == "Owned JSON description"
    assert compound.type == spec.OpenAPIType.OBJECT
    assert compound.one_of == [branch, spec.Schema(type=spec.OpenAPIType.OBJECT)]
    assert detail.description
    assert owned.description == "Owned detail"
    assert mixed.type is None
    assert success.properties is not None
    assert success.properties["detail"].description is None


def test_fastapi_preserves_owned_descriptions() -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(api_metadata_enabled=True, service_debug=False)
    ).bootstrap()
    cached: typing.Final = application.openapi()
    cached.clear()
    cached.update(
        {
            "components": {
                "schemas": {
                    "HTTPValidationError": {
                        "description": "Owned model",
                        "properties": {"detail": {"description": "Owned field"}},
                    },
                    "JsonValue": {"description": "Owned JSON description"},
                }
            },
        }
    )
    document: typing.Final = application.openapi()
    assert document["components"]["schemas"]["HTTPValidationError"]["description"] == "Owned model"
    assert (
        document["components"]["schemas"]["HTTPValidationError"]["properties"]["detail"]["description"] == "Owned field"
    )
    assert document["components"]["schemas"]["JsonValue"]["description"] == "Owned JSON description"


@pytest.mark.parametrize("enabled", [False, True])
def test_fastapi_setting_controls_generated_descriptions(enabled: bool) -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(api_metadata_enabled=enabled, service_debug=False)
    ).bootstrap()

    @application.post("/items")
    def create_item(payload: Payload) -> Payload:
        return payload

    document: typing.Final = application.openapi()
    assert ("description" in document["components"]["schemas"]["HTTPValidationError"]) is enabled
    assert "security" not in document
    with FastAPITestClient(application) as client:
        assert client.post("/items", json={"value": 1}).json() == {"value": 1}
    application.openapi_schema = None
    assert application.openapi() == document


@pytest.mark.parametrize("enabled", [False, True])
def test_litestar_setting_controls_generated_descriptions(enabled: bool) -> None:
    @litestar.get("/items", sync_to_thread=False)
    def get_items(limit: int) -> int:
        return limit

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(service_debug=False, api_metadata_enabled=enabled))
        .configure_application(LitestarConfig(route_handlers=[get_items]))
        .bootstrap()
    )
    document: typing.Final = application.openapi_schema.to_schema()
    error: typing.Final = document["paths"]["/items"]["get"]["responses"]["400"]["content"]["application/json"][
        "schema"
    ]
    assert ("description" in error["properties"]["detail"]) is enabled
    assert "security" not in document
    with LitestarTestClient(application) as client:
        assert client.get("/items?limit=1").json() == 1


def test_litestar_missing_openapi_and_empty_schema_are_supported() -> None:
    instrument: typing.Final = LitestarBootstrapper(LitestarSettings(api_metadata_enabled=True, service_debug=False))
    disabled: typing.Final = litestar.Litestar(openapi_config=None)
    assert instrument.bootstrap_after(disabled) is disabled
    application: typing.Final = litestar.Litestar(route_handlers=[])
    application.openapi_schema.components.schemas = {"JsonValue": spec.Schema()}
    application.openapi_schema.paths = None
    instrument.bootstrap_after(application)
    assert application.openapi_schema.components.schemas["JsonValue"].description
    application.openapi_schema.components.schemas = {}
    instrument.bootstrap_after(application)


def test_environment_can_enable_descriptions(monkeypatch: pytest.MonkeyPatch) -> None:
    assert FastApiSettings().api_metadata_enabled is False
    assert LitestarSettings().api_metadata_enabled is False
    assert "openapi_descriptions_enabled" not in FastApiSettings.model_fields
    assert "openapi_descriptions_enabled" not in LitestarSettings.model_fields
    monkeypatch.setenv("API_METADATA_ENABLED", "true")
    assert FastApiSettings().api_metadata_enabled is True
    assert LitestarSettings().api_metadata_enabled is True
