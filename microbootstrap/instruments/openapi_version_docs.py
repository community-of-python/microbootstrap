from __future__ import annotations
import re
import typing

import pydantic


SUPPORTED_HTTP_METHODS: typing.Final = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})
SAFE_MEDIA_TYPE_TOKEN: typing.Final[re.Pattern[str]] = re.compile(r"[!#$%&'*+\-.^_|~0-9A-Za-z]+\Z")
VENDOR_MEDIA_TYPE: typing.Final = re.compile(r"application/vnd\.([!#$%&'*+\-.^_|~0-9A-Za-z]+)\+json\Z")


class OpenApiOperationVersionOverride(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    path: str
    method: str
    supported_versions: tuple[str, ...]

    @pydantic.field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or "?" in value or "#" in value:
            message = "Operation path must be an absolute path without a query string or fragment."
            raise ValueError(message)
        return value

    @pydantic.field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        if value not in SUPPORTED_HTTP_METHODS:
            message = f"Operation method must be one of: {', '.join(sorted(SUPPORTED_HTTP_METHODS))}."
            raise ValueError(message)
        return value

    @pydantic.field_validator("supported_versions")
    @classmethod
    def validate_supported_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_versions(value)


class OpenApiVersionDocsConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    vendor_media_type: str
    supported_versions: tuple[str, ...]
    operation_versions: tuple[OpenApiOperationVersionOverride, ...] = ()

    @pydantic.field_validator("vendor_media_type")
    @classmethod
    def validate_vendor_media_type(cls, value: str) -> str:
        if VENDOR_MEDIA_TYPE.fullmatch(value) is None:
            message = "Vendor media type must use the application/vnd.<name>+json form."
            raise ValueError(message)
        return value

    @pydantic.field_validator("supported_versions")
    @classmethod
    def validate_supported_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated_versions = validate_versions(value)
        if not validated_versions:
            message = "OpenAPI version documentation requires at least one supported API version."
            raise ValueError(message)
        return validated_versions

    @pydantic.field_validator("operation_versions")
    @classmethod
    def validate_operation_versions(
        cls,
        value: tuple[OpenApiOperationVersionOverride, ...],
    ) -> tuple[OpenApiOperationVersionOverride, ...]:
        selectors = {(override.path, override.method) for override in value}
        if len(value) != len(selectors):
            message = "Operation version overrides must not contain duplicate path and method pairs."
            raise ValueError(message)
        return value


def validate_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        message = "Supported API versions must not contain duplicates."
        raise ValueError(message)
    if any(SAFE_MEDIA_TYPE_TOKEN.fullmatch(version) is None for version in value):
        message = "Each supported API version must be a non-empty safe media-type token."
        raise ValueError(message)
    return value
