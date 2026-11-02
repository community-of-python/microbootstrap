from __future__ import annotations
import dataclasses
import typing

from litestar.params import KwargDefinition, ParameterKwarg
from litestar.plugins import OpenAPISchemaPlugin
from litestar.typing import FieldDefinition

from microbootstrap.instruments.litestar_pydantic_descriptions import fetch_field_description


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.openapi import spec


def _describe_typed_dict_field(field_name: str, annotation: object) -> FieldDefinition:
    original_field: typing.Final = FieldDefinition.from_kwarg(annotation, field_name)
    original_keyword: typing.Final = original_field.kwarg_definition
    description: typing.Final = fetch_field_description(original_field)
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
