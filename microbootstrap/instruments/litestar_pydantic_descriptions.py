from __future__ import annotations
import dataclasses
import inspect
import typing

import pydantic
from litestar.params import KwargDefinition, ParameterKwarg
from litestar.plugins import OpenAPISchemaPlugin
from litestar.plugins.pydantic import PydanticSchemaPlugin
from litestar.typing import FieldDefinition
from pydantic.fields import FieldInfo


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.openapi import spec


def _fetch_field_description(field_definition: FieldDefinition) -> str | None:
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


@typing.final
class PydanticDescriptionsSchemaPlugin(PydanticSchemaPlugin):
    def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
        generated_schema: typing.Final = super().to_openapi_schema(field_definition, schema_creator)
        model_type: typing.Final = field_definition.annotation
        if isinstance(model_type, type) and issubclass(model_type, pydantic.BaseModel):
            model_description: typing.Final = model_type.__dict__.get("__doc__")
            if not generated_schema.description:
                generated_schema.description = _fetch_field_description(field_definition) or (
                    inspect.cleandoc(model_description) if isinstance(model_description, str) else None
                )
        return generated_schema


def _describe_typed_dict_field(field_name: str, annotation: object) -> FieldDefinition:
    original_field: typing.Final = FieldDefinition.from_kwarg(annotation, field_name)
    original_keyword: typing.Final = original_field.kwarg_definition
    description: typing.Final = _fetch_field_description(original_field)
    if not description or (original_keyword is not None and not isinstance(original_keyword, KwargDefinition)):
        return original_field
    return dataclasses.replace(
        original_field,
        kwarg_definition=dataclasses.replace(
            original_keyword if isinstance(original_keyword, KwargDefinition) else ParameterKwarg(),
            description=description,
        ),
    )


@typing.final
class PydanticTypedDictDescriptionsPlugin(OpenAPISchemaPlugin):
    def is_plugin_supported_field(self, field_definition: FieldDefinition) -> bool:
        return field_definition.is_typeddict_type

    def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
        return schema_creator.create_component_schema(
            field_definition,
            required=sorted(field_definition.type_.__required_keys__),
            property_fields={
                field_name: _describe_typed_dict_field(field_name, annotation)
                for field_name, annotation in field_definition.get_type_hints(
                    include_extras=True, resolve_generics=True
                ).items()
            },
        )
