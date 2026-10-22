import copy
import http
import typing

import fastapi
import pydantic
from fastapi.testclient import TestClient

from microbootstrap.openapi.fastapi import update_openapi


class Payload(pydantic.BaseModel):
    value: pydantic.JsonValue


def test_generated_metadata_preserves_validation_and_is_idempotent() -> None:
    application: typing.Final = fastapi.FastAPI()

    @application.post("/items")
    def create_item(payload: Payload) -> Payload:
        return payload

    before: typing.Final = copy.deepcopy(application.openapi())
    update_openapi(application)
    after: typing.Final = copy.deepcopy(application.openapi())
    update_openapi(application)
    assert application.openapi() == after
    assert "security" not in after
    schemas: typing.Final = after["components"]["schemas"]
    assert schemas["JsonValue"]["description"].startswith("JSON value:")
    assert schemas["HTTPValidationError"]["properties"]["detail"]["description"]
    assert schemas["ValidationError"]["properties"]["loc"]["description"]
    for name in ("HTTPValidationError", "ValidationError"):
        assert schemas[name].get("required") == before["components"]["schemas"][name].get("required")
        assert set(schemas[name]["properties"]) == set(before["components"]["schemas"][name]["properties"])
    with TestClient(application) as client:
        assert client.post("/items", json={"value": {"nested": [1, None]}}).json() == {"value": {"nested": [1, None]}}
        rejected = client.post("/items", json={})
    assert rejected.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert set(rejected.json()) == {"detail"}
    assert "title" not in schemas["HTTPValidationError"]["properties"]


def test_no_routes_or_schema_components_are_required() -> None:
    application: typing.Final = fastapi.FastAPI()
    update_openapi(application, security=[], security_schemes={}, parameter_descriptions={})
    assert application.openapi()["security"] == []
    assert application.openapi()["components"]["schemas"] == {}


def test_caller_metadata_preserves_existing_descriptions_and_security() -> None:
    application: typing.Final = fastapi.FastAPI()
    document: typing.Final = application.openapi()
    document.update(
        {
            "security": [{"existing": []}],
            "components": {
                "schemas": {
                    "HTTPValidationError": {
                        "description": "Owned model",
                        "properties": {"detail": {"description": "Owned field"}},
                    },
                    "JsonValue": {"description": "Owned JSON description"},
                },
                "securitySchemes": {"existing": {"type": "http", "scheme": "bearer"}},
            },
            "paths": {
                "/items": {
                    "parameters": [{"name": "shared", "in": "query"}],
                    "get": {
                        "parameters": [
                            {"name": "item_id", "in": "query"},
                            {"name": "owned", "in": "query", "description": "Owned parameter"},
                            {"$ref": "#/components/parameters/External"},
                            {"name": "unmapped", "in": "query"},
                        ]
                    },
                    "post": {"parameters": [{"name": "item_id", "in": "query"}]},
                }
            },
        }
    )
    update_openapi(
        application,
        security=[],
        security_schemes={
            "existing": {"type": "apiKey", "in": "header", "name": "X-Key"},
            "new": {"type": "http", "scheme": "bearer"},
        },
        parameter_descriptions={"shared": "Shared value", "item_id": "Item identifier", "owned": "Replacement"},
    )
    assert document["security"] == [{"existing": []}]
    assert document["components"]["securitySchemes"]["existing"]["type"] == "http"
    assert document["components"]["securitySchemes"]["new"]["scheme"] == "bearer"
    assert document["components"]["schemas"]["HTTPValidationError"]["description"] == "Owned model"
    assert (
        document["components"]["schemas"]["HTTPValidationError"]["properties"]["detail"]["description"] == "Owned field"
    )
    assert document["components"]["schemas"]["JsonValue"]["description"] == "Owned JSON description"
    path_item: typing.Final = document["paths"]["/items"]
    assert path_item["parameters"][0]["description"] == "Shared value"
    assert path_item["get"]["parameters"][0]["description"] == "Item identifier"
    assert path_item["post"]["parameters"][0]["description"] == "Item identifier"
    assert path_item["get"]["parameters"][1]["description"] == "Owned parameter"
    assert "description" not in path_item["get"]["parameters"][2]
    assert "description" not in path_item["get"]["parameters"][3]
