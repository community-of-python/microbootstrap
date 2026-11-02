from __future__ import annotations
import http
import typing

import litestar
import pydantic
import pytest
from litestar.plugins.pydantic import PydanticPlugin
from litestar.testing import TestClient

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig


if typing.TYPE_CHECKING:
    from litestar.handlers import HTTPRouteHandler


_MAX_SCALAR_VALUE: typing.Final = 3
_MAX_SEQUENCE_ITEMS: typing.Final = 3


@typing.final
class ScalarRoot(pydantic.RootModel[int]):
    """A bounded numeric payload."""

    root: int = pydantic.Field(ge=1, le=_MAX_SCALAR_VALUE, description="Numeric payload.", examples=[2])


class RootExampleConfig(pydantic.ConfigDict):
    example: int


@typing.final
class ConfiguredExamplesRoot(pydantic.RootModel[int]):
    model_config: typing.ClassVar[RootExampleConfig] = {"example": 3}
    root: int = pydantic.Field(ge=1, le=_MAX_SCALAR_VALUE, examples=[2])


@typing.final
class ArrayRoot(pydantic.RootModel[list[ScalarRoot]]):
    """An ordered numeric payload."""

    root: list[ScalarRoot] = pydantic.Field(min_length=1, max_length=_MAX_SEQUENCE_ITEMS, description="Numeric values.")


@typing.final
class CatalogRecord(pydantic.BaseModel):
    identifier: str = pydantic.Field(description="Record identifier.")


@typing.final
class ObjectRoot(pydantic.RootModel[CatalogRecord]):
    """A record without a wrapper."""


@typing.final
class NestedRoot(pydantic.RootModel[ArrayRoot]):
    """Nested numeric payload."""


@typing.final
class RecursiveRoot(pydantic.RootModel[object]):
    """A recursively nested sequence."""

    root: list[RecursiveRoot]


@typing.final
class AliasedRoot(pydantic.RootModel[int]):
    root: int = pydantic.Field(alias="payload", ge=1)


@typing.final
class WrappedRoots(pydantic.BaseModel):
    scalar: ScalarRoot
    sequence: ArrayRoot
    record: ObjectRoot
    nested: NestedRoot
    recursive: RecursiveRoot


@litestar.post("/scalar", sync_to_thread=False)
def create_scalar(data: ScalarRoot) -> ScalarRoot:
    return data


@litestar.post("/configured", sync_to_thread=False)
def create_configured(data: ConfiguredExamplesRoot) -> ConfiguredExamplesRoot:
    return data


@litestar.post("/sequence", sync_to_thread=False)
def create_sequence(data: ArrayRoot) -> ArrayRoot:
    return data


@litestar.post("/record", sync_to_thread=False)
def create_record(data: ObjectRoot) -> ObjectRoot:
    return data


@litestar.post("/nested", sync_to_thread=False)
def create_nested(data: NestedRoot) -> NestedRoot:
    return data


@litestar.post("/recursive", sync_to_thread=False)
def create_recursive(data: RecursiveRoot) -> RecursiveRoot:
    return data


@litestar.post("/aliased", sync_to_thread=False)
def create_aliased(data: AliasedRoot) -> AliasedRoot:
    return data


@litestar.post("/wrapped", sync_to_thread=False)
def create_wrapped(data: WrappedRoots) -> WrappedRoots:
    return data


def _build_application(route_handler: HTTPRouteHandler, *, prefer_alias: bool = False) -> litestar.Litestar:
    return (
        LitestarBootstrapper(
            LitestarSettings(api_metadata_enabled=True, service_debug=False, health_checks_enabled=False)
        )
        .configure_application(
            LitestarConfig(route_handlers=[route_handler], plugins=[PydanticPlugin(prefer_alias=prefer_alias)])
        )
        .bootstrap()
    )


def _resolve_schema(
    document: dict[str, pydantic.JsonValue], schema_value: dict[str, pydantic.JsonValue]
) -> dict[str, pydantic.JsonValue]:
    reference_value: typing.Final = schema_value.get("$ref")
    if not isinstance(reference_value, str):
        return schema_value
    object_adapter: typing.Final = pydantic.TypeAdapter(dict[str, pydantic.JsonValue])
    components: typing.Final = object_adapter.validate_python(document.get("components"))
    schemas: typing.Final = object_adapter.validate_python(components.get("schemas"))
    return object_adapter.validate_python(schemas.get(reference_value.rsplit("/", maxsplit=1)[-1]))


@pytest.mark.parametrize(
    ("route_handler", "route_path", "request_value", "schema_type"),
    [
        (create_scalar, "/scalar", 2, "integer"),
        (create_sequence, "/sequence", [2], "array"),
        (create_record, "/record", {"identifier": "catalog-entry"}, "object"),
        (create_nested, "/nested", [2], "array"),
        (create_recursive, "/recursive", [[], [[]]], "array"),
    ],
)
def test_litestar_root_schema_matches_the_wire_value(
    route_handler: HTTPRouteHandler, route_path: str, request_value: object, schema_type: str
) -> None:
    application: typing.Final = _build_application(route_handler)
    document: typing.Final = application.openapi_schema.to_schema()
    operation: typing.Final = document["paths"][route_path]["post"]
    request_schema: typing.Final = _resolve_schema(
        document, operation["requestBody"]["content"]["application/json"]["schema"]
    )
    response_schema: typing.Final = _resolve_schema(
        document, operation["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert request_schema["type"] == response_schema["type"] == schema_type
    response_properties: typing.Final = response_schema.get("properties")
    assert not isinstance(response_properties, dict) or "root" not in response_properties
    with TestClient(application) as test_client:
        response: typing.Final = test_client.post(route_path, json=request_value)
    assert response.status_code == http.HTTPStatus.CREATED
    assert response.json() == request_value


def test_litestar_nested_root_models_keep_constraints_and_recursive_references() -> None:
    application: typing.Final = _build_application(create_wrapped)
    document: typing.Final = application.openapi_schema.to_schema()
    components: typing.Final = document["components"]["schemas"]
    scalar_schema: typing.Final = components["ScalarRoot"]
    assert scalar_schema["minimum"] == 1
    assert scalar_schema["maximum"] == _MAX_SCALAR_VALUE
    assert scalar_schema["examples"] == [2]
    assert scalar_schema["description"] == "A bounded numeric payload."
    assert components["ArrayRoot"]["minItems"] == 1
    assert components["ArrayRoot"]["maxItems"] == _MAX_SEQUENCE_ITEMS
    assert components["ObjectRoot"]["required"] == ["identifier"]
    assert components["NestedRoot"]["description"] == "Nested numeric payload."
    assert _resolve_schema(document, components["ArrayRoot"]["items"])["type"] == "integer"
    assert components["RecursiveRoot"]["items"] == {"$ref": "#/components/schemas/RecursiveRoot"}
    wrapped_schema: typing.Final = components["WrappedRoots"]
    for property_name, expected_type in (
        ("scalar", "integer"),
        ("sequence", "array"),
        ("record", "object"),
        ("nested", "array"),
        ("recursive", "array"),
    ):
        assert _resolve_schema(document, wrapped_schema["properties"][property_name])["type"] == expected_type
    request_payload: typing.Final = {
        "scalar": 2,
        "sequence": [2],
        "record": {"identifier": "catalog-entry"},
        "nested": [2],
        "recursive": [[], [[]]],
    }
    with TestClient(application) as test_client:
        accepted: typing.Final = test_client.post("/wrapped", json=request_payload)
        rejected_scalar: typing.Final = test_client.post("/wrapped", json=request_payload | {"scalar": 0})
        rejected_sequence: typing.Final = test_client.post("/wrapped", json=request_payload | {"sequence": []})
    assert accepted.status_code == http.HTTPStatus.CREATED
    assert accepted.json() == request_payload
    assert rejected_scalar.status_code == rejected_sequence.status_code == http.HTTPStatus.BAD_REQUEST


def test_litestar_root_field_alias_does_not_add_an_envelope() -> None:
    application: typing.Final = _build_application(create_aliased, prefer_alias=True)
    document: typing.Final = application.openapi_schema.to_schema()
    root_schema: typing.Final = document["components"]["schemas"]["AliasedRoot"]
    assert root_schema["type"] == "integer"
    assert root_schema["minimum"] == 1
    assert "properties" not in root_schema
    root_value: typing.Final = 2
    with TestClient(application) as test_client:
        response: typing.Final = test_client.post("/aliased", json=root_value)
    assert response.status_code == http.HTTPStatus.CREATED
    assert response.json() == root_value


def test_litestar_root_model_examples_override_root_field_examples() -> None:
    application: typing.Final = _build_application(create_configured)
    document: typing.Final = application.openapi_schema.to_schema()
    root_schema: typing.Final = document["components"]["schemas"]["ConfiguredExamplesRoot"]
    configured_example: typing.Final = 3
    assert root_schema["examples"] == [configured_example]
    assert root_schema["type"] == "integer"
    with TestClient(application) as test_client:
        response: typing.Final = test_client.post("/configured", json=configured_example)
    assert response.status_code == http.HTTPStatus.CREATED
    assert response.json() == configured_example
