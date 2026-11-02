from __future__ import annotations
import dataclasses
import typing

from litestar.openapi import spec


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator


def populate_root_value_schema(
    generated_schema: spec.Schema, schema_creator: SchemaCreator, root_field_name: str
) -> None:
    root_schema: typing.Final = (generated_schema.properties or {})[root_field_name]
    value_schema: typing.Final = (
        schema_creator.schema_registry.from_reference(root_schema).schema
        if isinstance(root_schema, spec.Reference)
        else root_schema
    )
    original_title: typing.Final = generated_schema.title
    original_examples: typing.Final = generated_schema.examples
    for schema_field in dataclasses.fields(spec.Schema):
        setattr(generated_schema, schema_field.name, getattr(value_schema, schema_field.name))
    generated_schema.title = original_title
    if original_examples is not None:
        generated_schema.examples = original_examples
