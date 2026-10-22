from __future__ import annotations
import typing

import pydantic
from litestar.openapi import spec

from microbootstrap.instruments.health_checks_instrument import HealthCheckTypedDict


if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


_ERROR_DESCRIPTIONS: typing.Final = {
    "status_code": "HTTP status code of the failed request.",
    "detail": "Human-readable explanation of the request failure.",
    "extra": "Additional validation or error details supplied by Litestar.",
}
_HEALTH_PROPERTIES: typing.Final[dict[str, str]] = {
    name: field["description"]
    for name, field in pydantic.TypeAdapter(HealthCheckTypedDict).json_schema()["properties"].items()
}
_HTTP_METHODS: typing.Final = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def _update_properties(schema: spec.Schema, descriptions: Mapping[str, str]) -> None:
    for name, description in descriptions.items():
        field = (schema.properties or {}).get(name)
        if isinstance(field, spec.Schema) and not field.description:
            field.description = description


def _update_error(schema: spec.Schema) -> None:
    for branch in (*(schema.one_of or []), *(schema.any_of or []), *(schema.all_of or [])):
        if isinstance(branch, spec.Schema):
            _update_error(branch)
    if (
        schema.type is None
        and schema.one_of
        and all(isinstance(branch, spec.Schema) and branch.type == spec.OpenAPIType.OBJECT for branch in schema.one_of)
    ):
        schema.type = spec.OpenAPIType.OBJECT
    _update_properties(schema, _ERROR_DESCRIPTIONS)


def _update_components(
    document: spec.OpenAPI,
    descriptions: Mapping[str, str | None],
    properties: Mapping[str, Mapping[str, str]],
) -> None:
    for name, schema in (document.components.schemas or {}).items():
        description = descriptions.get(name)
        if description and not schema.description:
            schema.description = description
        default_properties = _HEALTH_PROPERTIES if name == "HealthCheckTypedDict" else {}
        _update_properties(schema, default_properties | dict(properties.get(name, {})))


def _update_parameters(parameters: Iterable[spec.Parameter | spec.Reference], descriptions: Mapping[str, str]) -> None:
    for parameter in parameters:
        if isinstance(parameter, spec.Parameter) and not parameter.description:
            parameter.description = descriptions.get(parameter.name)


def _update_operation(operation: spec.Operation, parameter_descriptions: Mapping[str, str]) -> None:
    _update_parameters(operation.parameters or [], parameter_descriptions)
    for code, response in (operation.responses or {}).items():
        if not str(code).startswith(("4", "5")) or not isinstance(response, spec.OpenAPIResponse):
            continue
        for media_type in (response.content or {}).values():
            if isinstance(media_type.schema, spec.Schema):
                _update_error(media_type.schema)


def update_openapi(
    document: spec.OpenAPI,
    *,
    schema_descriptions: Mapping[str, str | None] | None = None,
    property_descriptions: Mapping[str, Mapping[str, str]] | None = None,
    parameter_descriptions: Mapping[str, str] | None = None,
    operation_security: Mapping[tuple[str, str], list[spec.SecurityRequirement]] | None = None,
) -> None:
    """Describe generated errors and fill caller-supplied metadata without changing handlers.

    Security overrides use (lowercase HTTP method, exact OpenAPI path) keys.
    No authentication scheme or domain-specific field meaning is inferred.
    """
    _update_components(
        document,
        {"JsonValue": "JSON value: an object, array, string, number, boolean or null."}
        | dict(schema_descriptions or {}),
        property_descriptions or {},
    )
    for path, path_item in (document.paths or {}).items():
        _update_parameters(path_item.parameters or [], parameter_descriptions or {})
        for method in _HTTP_METHODS:
            operation = getattr(path_item, method)
            if operation is None:
                continue
            if operation_security is not None and (method, path) in operation_security:
                operation.security = operation_security[method, path]
            _update_operation(operation, parameter_descriptions or {})
