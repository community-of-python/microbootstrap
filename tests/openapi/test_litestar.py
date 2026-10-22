import copy
import http
import typing

import litestar
from litestar.openapi import spec
from litestar.testing import TestClient

from microbootstrap.instruments.health_checks_instrument import HealthCheckTypedDict
from microbootstrap.openapi.litestar import update_openapi


def _document(
    *,
    components: spec.Components | None = None,
    paths: dict[str, spec.PathItem] | None = None,
) -> spec.OpenAPI:
    return spec.OpenAPI(
        info=spec.Info(title="Example API", version="1"),
        servers=[],
        components=components or spec.Components(),
        paths=paths,
    )


def test_real_errors_and_health_schemas_preserve_runtime_contracts() -> None:
    @litestar.get("/health", sync_to_thread=False)
    def get_health() -> HealthCheckTypedDict:
        return {"health_status": True}

    @litestar.get("/items/{item_id:int}", sync_to_thread=False)
    def get_item(item_id: int, limit: int = 1) -> int:
        return item_id * limit

    application: typing.Final = litestar.Litestar(route_handlers=[get_health, get_item])
    document: typing.Final = application.openapi_schema
    before: typing.Final = copy.deepcopy(document.to_schema())
    update_openapi(document)
    after: typing.Final = copy.deepcopy(document.to_schema())
    update_openapi(document)
    assert document.to_schema() == after
    health: typing.Final = after["components"]["schemas"]["HealthCheckTypedDict"]
    assert health["properties"]["health_status"]["description"].startswith("Static process health")
    error: typing.Final = after["paths"]["/items/{item_id}"]["get"]["responses"]["400"]["content"]["application/json"][
        "schema"
    ]
    assert error["properties"]["detail"]["description"]
    assert "title" not in error["properties"]
    before_error: typing.Final = before["paths"]["/items/{item_id}"]["get"]["responses"]["400"]["content"][
        "application/json"
    ]["schema"]
    assert error["required"] == before_error["required"]
    assert set(error["properties"]) == set(before_error["properties"])
    item_id: typing.Final = 42
    with TestClient(application) as client:
        assert client.get("/health").json() == {"health_status": True}
        assert client.get(f"/items/{item_id}").json() == item_id
        rejected = client.get(f"/items/{item_id}?limit=invalid")
    assert rejected.status_code == http.HTTPStatus.BAD_REQUEST
    assert set(rejected.json()) == {"status_code", "detail", "extra"}


def test_empty_document_and_components_are_supported() -> None:
    update_openapi(_document())
    update_openapi(_document(components=spec.Components()))


def test_component_and_operation_overrides_are_explicit_and_preserve_owned_metadata() -> None:
    field: typing.Final = spec.Schema(type=spec.OpenAPIType.STRING)
    owned_field: typing.Final = spec.Schema(description="Owned field")
    schema: typing.Final = spec.Schema(
        properties={"value": field, "owned": owned_field, "reference": spec.Reference(ref="#/components/schemas/Other")}
    )
    owned: typing.Final = spec.Schema(description="Owned schema")
    parameter: typing.Final = spec.Parameter(name="item_id", param_in="query")
    shared: typing.Final = spec.Parameter(name="shared", param_in="query")
    owned_parameter: typing.Final = spec.Parameter(name="owned", param_in="query", description="Owned parameter")
    unmapped: typing.Final = spec.Parameter(name="unmapped", param_in="query")
    protected: typing.Final = spec.Operation(security=[{"existing": []}])
    selected: typing.Final = spec.Operation(
        parameters=[parameter, owned_parameter, unmapped, spec.Reference(ref="#/components/parameters/External")]
    )
    document: typing.Final = _document(
        components=spec.Components(schemas={"Custom": schema, "Owned": owned, "JsonValue": spec.Schema()}),
        paths={"/items": spec.PathItem(get=protected, post=selected, parameters=[shared])},
    )
    update_openapi(
        document,
        schema_descriptions={"Custom": "Caller schema", "Owned": "Replacement", "Absent": None},
        property_descriptions={"Custom": {"value": "Caller value", "owned": "Replacement", "missing": "Ignored"}},
        parameter_descriptions={"item_id": "Item identifier", "shared": "Shared value", "owned": "Replacement"},
        operation_security={("post", "/items"): [], ("delete", "/absent"): []},
    )
    assert schema.description == "Caller schema"
    assert field.description == "Caller value"
    assert owned.description == "Owned schema"
    assert owned_field.description == "Owned field"
    assert parameter.description == "Item identifier"
    assert shared.description == "Shared value"
    assert owned_parameter.description == "Owned parameter"
    assert unmapped.description is None
    assert selected.security == []
    assert protected.security == [{"existing": []}]


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
    document: typing.Final = _document(paths={"/items": spec.PathItem(get=operation)})
    update_openapi(document)
    assert compound.type == spec.OpenAPIType.OBJECT
    assert compound.one_of == [branch, spec.Schema(type=spec.OpenAPIType.OBJECT)]
    assert detail.description
    assert owned.description == "Owned detail"
    assert mixed.type is None
    assert success.properties is not None
    assert success.properties["detail"].description is None
