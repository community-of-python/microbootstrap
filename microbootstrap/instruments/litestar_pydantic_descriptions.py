from __future__ import annotations
import dataclasses
import inspect
import typing

import pydantic
from litestar.openapi import spec
from litestar.params import KwargDefinition
from litestar.plugins.pydantic import PydanticSchemaPlugin
from pydantic.fields import FieldInfo


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.typing import FieldDefinition


def fetch_field_description(field_definition: FieldDefinition) -> str | None:
    keyword_definition: typing.Final = field_definition.kwarg_definition
    if isinstance(keyword_definition, KwargDefinition) and keyword_definition.description:
        return keyword_definition.description
    return next(
        (
            metadata.description
            for metadata in reversed(field_definition.metadata)
            if isinstance(metadata, FieldInfo) and metadata.description
        ),
        None,
    )


def _unwrap_root_schema(generated_schema: spec.Schema, schema_creator: SchemaCreator, root_field_name: str) -> None:
    root_schema: typing.Final = (generated_schema.properties or {})[root_field_name]
    value_schema: typing.Final = (
        schema_creator.schema_registry.from_reference(root_schema).schema
        if isinstance(root_schema, spec.Reference)
        else root_schema
    )
    original_title: typing.Final = generated_schema.title
    for schema_field in dataclasses.fields(spec.Schema):
        setattr(generated_schema, schema_field.name, getattr(value_schema, schema_field.name))
    generated_schema.title = original_title


@typing.final
class PydanticDescriptionsSchemaPlugin(PydanticSchemaPlugin):
    def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
        generated_schema: typing.Final = super().to_openapi_schema(field_definition, schema_creator)
        model_type: typing.Final = field_definition.annotation
        if isinstance(model_type, type) and issubclass(model_type, pydantic.BaseModel):
            model_description: typing.Final = model_type.__dict__.get("__doc__")
            owner_description: typing.Final = fetch_field_description(field_definition) or (
                inspect.cleandoc(model_description) if isinstance(model_description, str) else None
            )
            if issubclass(model_type, pydantic.RootModel):
                root_field: typing.Final = model_type.model_fields["root"]
                root_field_name: typing.Final = root_field.alias if schema_creator.prefer_alias else None
                _unwrap_root_schema(generated_schema, schema_creator, root_field_name or "root")
                generated_schema.description = owner_description or generated_schema.description
            elif not generated_schema.description:
                generated_schema.description = owner_description
        return generated_schema
