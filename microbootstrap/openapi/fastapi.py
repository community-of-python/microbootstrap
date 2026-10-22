from __future__ import annotations
import typing


if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    import fastapi


_VALIDATION_DESCRIPTIONS: typing.Final = {
    "detail": "Validation errors describing the rejected request fields.",
    "loc": "Field names and array indices locating the invalid input.",
    "msg": "Human-readable validation error message.",
    "type": "Machine-readable validation error category.",
    "input": "Input value associated with the validation failure.",
    "ctx": "Additional context explaining the validation error.",
}
_HTTP_METHODS: typing.Final = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def _update_parameters(document: dict[str, typing.Any], descriptions: Mapping[str, str]) -> None:
    for path_item in document.get("paths", {}).values():
        parameter_groups = [path_item.get("parameters", [])]
        parameter_groups.extend(path_item.get(method, {}).get("parameters", []) for method in _HTTP_METHODS)
        for parameters in parameter_groups:
            for parameter in parameters:
                description = descriptions.get(parameter.get("name", ""))
                if description:
                    parameter.setdefault("description", description)


def update_openapi(
    application: fastapi.FastAPI,
    *,
    security: list[dict[str, list[str]]] | None = None,
    security_schemes: Mapping[str, dict[str, typing.Any]] | None = None,
    parameter_descriptions: Mapping[str, str] | None = None,
) -> None:
    """Enrich the cached schema after all routes are registered, preserving existing metadata.

    Authentication declarations and parameter meanings come from the caller;
    this helper neither infers authorization nor changes request handling.
    Parameter descriptions apply to matching names throughout the document.
    """
    document: typing.Final = application.openapi()
    schemas: typing.Final = document.setdefault("components", {}).setdefault("schemas", {})
    for name in ("HTTPValidationError", "ValidationError"):
        if name not in schemas:
            continue
        definition = schemas[name]
        definition.setdefault("description", "Request validation failure reported by FastAPI.")
        for field_name, description in _VALIDATION_DESCRIPTIONS.items():
            if field_name in definition.get("properties", {}):
                definition["properties"][field_name].setdefault("description", description)
    if "JsonValue" in schemas:
        schemas["JsonValue"].setdefault("description", "JSON value: an object, array, string, number, boolean or null.")
    if security is not None:
        document.setdefault("security", security)
    if security_schemes:
        definitions = document["components"].setdefault("securitySchemes", {})
        for name, scheme in security_schemes.items():
            definitions.setdefault(name, scheme)
    if parameter_descriptions:
        _update_parameters(document, parameter_descriptions)
