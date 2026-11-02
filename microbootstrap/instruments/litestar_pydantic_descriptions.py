from __future__ import annotations
import inspect
import typing

import pydantic
from litestar.params import KwargDefinition
from litestar.plugins.pydantic import PydanticSchemaPlugin
from pydantic.fields import FieldInfo

from microbootstrap.instruments.litestar_root_schema import populate_root_value_schema


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.openapi import spec
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


@typing.final
class PydanticDescriptionsSchemaPlugin(PydanticSchemaPlugin):
    def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
        configured_plugin: typing.Final = next(
            (
                plugin
                for plugin in schema_creator.plugins
                if not isinstance(plugin, PydanticDescriptionsSchemaPlugin)
                and schema_creator.plugin_supports_field(plugin, field_definition)
            ),
            None,
        )
        if configured_plugin is not None and type(configured_plugin) is not PydanticSchemaPlugin:
            return configured_plugin.to_openapi_schema(field_definition, schema_creator)
        model_schema: typing.Final = (
            configured_plugin.to_openapi_schema(field_definition, schema_creator)
            if configured_plugin is not None
            else super().to_openapi_schema(field_definition, schema_creator)
        )
        model_type: typing.Final = field_definition.annotation
        if isinstance(model_type, type) and issubclass(model_type, pydantic.BaseModel):
            model_description: typing.Final = model_type.__dict__.get("__doc__")
            owner_description: typing.Final = fetch_field_description(field_definition) or (
                inspect.cleandoc(model_description) if isinstance(model_description, str) else None
            )
            if issubclass(model_type, pydantic.RootModel):
                root_field: typing.Final = model_type.model_fields["root"]
                root_field_name: typing.Final = root_field.alias if schema_creator.prefer_alias else None
                populate_root_value_schema(model_schema, schema_creator, root_field_name or "root")
                model_schema.description = owner_description or model_schema.description
            elif not model_schema.description:
                model_schema.description = owner_description
        return model_schema
