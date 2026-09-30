from __future__ import annotations
import re
import typing

import pydantic


SUPPORTED_HTTP_METHODS: typing.Final = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})
SAFE_MEDIA_TYPE_TOKEN: typing.Final[re.Pattern[str]] = re.compile(r"[!#$%&'*+\-.^_|~0-9A-Za-z]+\Z")
VENDOR_MEDIA_TYPE: typing.Final = re.compile(r"application/vnd\.([!#$%&'*+\-.^_|~0-9A-Za-z]+)\+json\Z")


class OpenApiOperationSelector(pydantic.BaseModel):
    path: str
    method: str

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


class OpenApiOperationVersionOverride(OpenApiOperationSelector):
    supported_versions: tuple[str, ...]

    @pydantic.field_validator("supported_versions")
    @classmethod
    def validate_supported_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated_versions = validate_versions(value)
        if not validated_versions:
            message = "Operation version overrides must contain at least one supported API version."
            raise ValueError(message)
        return validated_versions


class OpenApiVersionDocsConfig(pydantic.BaseModel):
    enabled: bool = False
    vendor_media_type: str | None = None
    supported_versions: tuple[str, ...] = ()
    suppressed_operations: tuple[OpenApiOperationSelector, ...] = ()
    operation_versions: tuple[OpenApiOperationVersionOverride, ...] = ()

    @pydantic.field_validator("vendor_media_type")
    @classmethod
    def validate_vendor_media_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if VENDOR_MEDIA_TYPE.fullmatch(value) is None:
            message = "Vendor media type must use the application/vnd.<name>+json form."
            raise ValueError(message)
        return value

    @pydantic.field_validator("supported_versions")
    @classmethod
    def validate_supported_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_versions(value)

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

    @pydantic.model_validator(mode="after")
    def validate_enabled_configuration(self) -> OpenApiVersionDocsConfig:
        if self.enabled and self.vendor_media_type is None:
            message = "Enabled OpenAPI version documentation requires an explicit vendor media type."
            raise ValueError(message)
        if self.enabled and not self.supported_versions:
            message = "Enabled OpenAPI version documentation requires at least one supported API version."
            raise ValueError(message)
        return self


def validate_versions(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        message = "Supported API versions must not contain duplicates."
        raise ValueError(message)
    if any(SAFE_MEDIA_TYPE_TOKEN.fullmatch(version) is None for version in value):
        message = "Each supported API version must be a non-empty safe media-type token."
        raise ValueError(message)
    return value


def get_supported_versions(
    configuration: OpenApiVersionDocsConfig,
    path: str,
    method: str,
) -> tuple[str, ...]:
    for override in configuration.operation_versions:
        if override.path == path and override.method == method:
            return override.supported_versions
    return configuration.supported_versions


def build_accept_versioning_extension(
    configuration: OpenApiVersionDocsConfig,
    supported_versions: tuple[str, ...],
) -> dict[str, str | list[str]]:
    assert configuration.vendor_media_type is not None  # noqa: S101 - enabled configuration guarantees this.
    return {
        "header": "Accept",
        "mediaType": configuration.vendor_media_type,
        "parameter": "version",
        "supportedVersions": list(supported_versions),
    }


def build_version_documentation(
    configuration: OpenApiVersionDocsConfig,
    supported_versions: tuple[str, ...],
) -> str:
    media_types: typing.Final = tuple(
        f"{configuration.vendor_media_type}; version={version}" for version in supported_versions
    )
    if len(media_types) == 1:
        return f"Supported API version: `{media_types[0]}`."
    return "Supported API versions:\n" + "\n".join(f"- `{media_type}`." for media_type in media_types)


def append_version_documentation(
    description: str | None,
    configuration: OpenApiVersionDocsConfig,
    supported_versions: tuple[str, ...],
) -> str:
    version_documentation: typing.Final = build_version_documentation(configuration, supported_versions)
    if description is None or not description:
        return version_documentation
    if version_documentation in description:
        return description
    return f"{description}\n\n{version_documentation}"


def is_operation_suppressed(
    configuration: OpenApiVersionDocsConfig,
    path: str,
    method: str,
) -> bool:
    return OpenApiOperationSelector(path=path, method=method) in configuration.suppressed_operations
