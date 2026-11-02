from __future__ import annotations
import copy
import http
import typing

import litestar
import pydantic
import pytest
import typing_extensions
from litestar.params import Parameter
from litestar.plugins.pydantic import PydanticPlugin, PydanticSchemaPlugin
from litestar.testing import TestClient

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.handlers import HTTPRouteHandler
    from litestar.openapi import spec
    from litestar.plugins import PluginProtocol
    from litestar.typing import FieldDefinition


@typing.final
class DocumentedRecord(pydantic.BaseModel):
    """One record returned by the catalog."""

    identifier: str = pydantic.Field(description="Record identifier.")


@typing.final
class RecordTree(pydantic.BaseModel):
    """A tree of catalog records."""

    children: list[RecordTree] = pydantic.Field(default_factory=list, description="Nested records.")


IntervalBoundaries = typing_extensions.TypedDict(
    "IntervalBoundaries",
    {
        "from": typing.Annotated[int | None, pydantic.Field(description="Lower interval bound.")],
        "to": typing.Annotated[
            int | None,
            pydantic.Field(description="Pydantic interval description."),
            Parameter(description="Explicit upper interval bound."),
        ],
        "label": typing_extensions.NotRequired[typing.Annotated[str, pydantic.Field(description="Interval label.")]],
        "unlabelled": typing_extensions.NotRequired[str],
    },
)


@typing.final
class RecordPayload(pydantic.BaseModel):
    """Catalog records and their selection interval."""

    records: list[DocumentedRecord] = pydantic.Field(description="Selected records.")
    selected: DocumentedRecord | None = pydantic.Field(default=None, description="Selected record, when available.")
    interval: IntervalBoundaries = pydantic.Field(description="Selection boundaries.")
    record_tree: RecordTree = pydantic.Field(description="Record hierarchy.")
    source_url: pydantic.AnyHttpUrl = pydantic.Field(description="Catalog source.")
    limit: int = pydantic.Field(ge=1, le=3, description="Maximum selected records.")


@typing.final
class AliasedRecord(pydantic.BaseModel):
    """An aliased catalog record."""

    record_id: str = pydantic.Field(alias="recordId", description="Public record identifier.")


@litestar.post("/records", sync_to_thread=False)
def create_records(data: RecordPayload) -> RecordPayload:
    return data


def _build_application(
    route_handler: HTTPRouteHandler,
    *,
    metadata_enabled: bool = True,
    plugins: list[PluginProtocol] | None = None,
) -> litestar.Litestar:
    return (
        LitestarBootstrapper(
            LitestarSettings(api_metadata_enabled=metadata_enabled, service_debug=False, health_checks_enabled=False)
        )
        .configure_application(LitestarConfig(route_handlers=[route_handler], plugins=plugins or []))
        .bootstrap()
    )


@pytest.mark.parametrize("metadata_enabled", [False, True])
def test_litestar_describes_nested_models_and_typed_dict_fields(metadata_enabled: bool) -> None:
    application: typing.Final = _build_application(create_records, metadata_enabled=metadata_enabled)
    document: typing.Final = application.openapi_schema.to_schema()
    component_schemas: typing.Final = document["components"]["schemas"]
    assert bool(component_schemas["RecordPayload"].get("description")) is metadata_enabled
    assert bool(component_schemas["DocumentedRecord"].get("description")) is metadata_enabled
    assert component_schemas["RecordTree"]["description"] == "Record hierarchy."
    interval_schema: typing.Final = component_schemas["IntervalBoundaries"]
    assert bool(interval_schema["properties"]["from"].get("description")) is metadata_enabled
    assert interval_schema["properties"]["to"]["description"] == "Explicit upper interval bound."
    assert bool(interval_schema["properties"]["label"].get("description")) is metadata_enabled
    assert "description" not in interval_schema["properties"]["unlabelled"]
    assert interval_schema["required"] == ["from", "to"]
    assert component_schemas["RecordTree"]["properties"]["children"]["items"] == {
        "$ref": "#/components/schemas/RecordTree"
    }
    assert document == application.openapi_schema.to_schema()


def _strip_descriptions(schema_value: object) -> object:
    if isinstance(schema_value, dict):
        return {key: _strip_descriptions(value) for key, value in schema_value.items() if key != "description"}
    if isinstance(schema_value, list):
        return [_strip_descriptions(value) for value in schema_value]
    return schema_value


@pytest.mark.parametrize("metadata_enabled", [False, True])
def test_litestar_descriptions_preserve_constraints_and_wire_values(metadata_enabled: bool) -> None:
    request_payload: typing.Final = {
        "records": [{"identifier": "catalog-entry"}],
        "selected": {"identifier": "catalog-entry"},
        "interval": {"from": None, "to": 2},
        "record_tree": {"children": [{"children": []}]},
        "source_url": "https://example.org/",
        "limit": 2,
    }
    baseline: typing.Final = _build_application(create_records, metadata_enabled=False)
    described: typing.Final = _build_application(create_records)
    baseline_document: typing.Final = baseline.openapi_schema.to_schema()
    described_document: typing.Final = described.openapi_schema.to_schema()
    for schema_name in ("RecordPayload", "DocumentedRecord", "RecordTree", "IntervalBoundaries"):
        assert _strip_descriptions(baseline_document["components"]["schemas"][schema_name]) == _strip_descriptions(
            described_document["components"]["schemas"][schema_name]
        )
    with TestClient(described if metadata_enabled else baseline) as test_client:
        accepted: typing.Final = test_client.post("/records", json=request_payload)
        invalid_payload: typing.Final = copy.deepcopy(request_payload)
        invalid_payload["limit"] = 0
        rejected: typing.Final = test_client.post("/records", json=invalid_payload)
    assert accepted.status_code == http.HTTPStatus.CREATED
    assert accepted.json() == request_payload
    assert rejected.status_code == http.HTTPStatus.BAD_REQUEST


def test_litestar_preserves_explicit_model_description() -> None:
    @litestar.get("/record", sync_to_thread=False)
    def fetch_record() -> typing.Annotated[DocumentedRecord, Parameter(description="Explicit record contract.")]:
        return DocumentedRecord(identifier="catalog-entry")

    application: typing.Final = _build_application(fetch_record)
    document: typing.Final = application.openapi_schema.to_schema()
    assert document["components"]["schemas"]["DocumentedRecord"]["description"] == "Explicit record contract."
    with TestClient(application) as test_client:
        assert test_client.get("/record").json() == {"identifier": "catalog-entry"}


def test_litestar_preserves_custom_schema_plugin() -> None:
    @typing.final
    class CustomRecordPlugin(PydanticSchemaPlugin):
        def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
            generated_schema: typing.Final = super().to_openapi_schema(field_definition, schema_creator)
            generated_schema.description = "Custom record contract."
            return generated_schema

    application: typing.Final = _build_application(create_records, plugins=[CustomRecordPlugin()])
    document: typing.Final = application.openapi_schema.to_schema()
    assert document["components"]["schemas"]["DocumentedRecord"]["description"] == "Custom record contract."


def test_litestar_preserves_pydantic_plugin_aliases() -> None:
    @litestar.get("/record", sync_to_thread=False)
    def fetch_record() -> AliasedRecord:
        return AliasedRecord(recordId="catalog-entry")

    application: typing.Final = _build_application(fetch_record, plugins=[PydanticPlugin(prefer_alias=True)])
    document: typing.Final = application.openapi_schema.to_schema()
    record_schema: typing.Final = document["components"]["schemas"]["AliasedRecord"]
    assert set(record_schema["properties"]) == {"recordId"}
    assert record_schema["description"] == "An aliased catalog record."
    with TestClient(application) as test_client:
        assert test_client.get("/record").json() == {"recordId": "catalog-entry"}
