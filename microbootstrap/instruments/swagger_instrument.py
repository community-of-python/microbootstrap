from __future__ import annotations
import re
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument
from microbootstrap.instruments.openapi_security_schemes import (
    OpenApiSecurityScheme,
    serialize_security_schemes,
)
from microbootstrap.instruments.openapi_version_docs import (
    SUPPORTED_HTTP_METHODS,
    OpenApiVersionDocsConfig,
)


SECURITY_SCHEME_NAME_PATTERN: typing.Final = re.compile(r"^[a-zA-Z0-9._-]+$")


class SwaggerConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"

    service_static_path: str = "/static"
    swagger_path: str = "/docs"
    swagger_offline_docs: bool = False
    swagger_extra_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    security_schemes: dict[str, OpenApiSecurityScheme] = pydantic.Field(default_factory=dict)
    openapi_version_docs: OpenApiVersionDocsConfig | None = None

    @pydantic.field_validator("security_schemes")
    @classmethod
    def validate_security_scheme_names(
        cls,
        security_schemes: dict[str, OpenApiSecurityScheme],
    ) -> dict[str, OpenApiSecurityScheme]:
        for scheme_name in security_schemes:
            if SECURITY_SCHEME_NAME_PATTERN.fullmatch(scheme_name) is None:
                message = "OpenAPI security scheme names must match ^[a-zA-Z0-9._-]+$."
                raise ValueError(message)
        return security_schemes


class SwaggerInstrument(Instrument[SwaggerConfig]):
    instrument_name = "Swagger"
    ready_condition = "Provide valid swagger_path"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.swagger_path) and is_valid_path(self.instrument_config.swagger_path)

    def _has_version_documentation(self) -> bool:
        configuration: typing.Final = self.instrument_config.openapi_version_docs
        return configuration is not None and configuration.enabled

    def _prepare_version_documentation(
        self,
        path: str,
        method: str,
        description: object,
        existing_extension: object,
        *,
        has_existing_extension: bool,
    ) -> tuple[dict[str, str | list[str]], str] | None:
        configuration: typing.Final = self.instrument_config.openapi_version_docs
        if (
            configuration is None
            or not configuration.enabled
            or method not in SUPPORTED_HTTP_METHODS
            or self._is_operation_suppressed(configuration, path, method)
        ):
            return None
        if description is not None and not isinstance(description, str):
            message = f"OpenAPI operation {method.upper()} {path} has a non-string description."
            raise ValueError(message)

        supported_versions: typing.Final = self._select_supported_versions(configuration, path, method)
        expected_extension: typing.Final = self._build_accept_versioning_extension(configuration, supported_versions)
        self._validate_accept_versioning_extension(
            existing_extension,
            expected_extension,
            has_existing_extension=has_existing_extension,
        )
        return expected_extension, self._append_version_documentation(description, configuration, supported_versions)

    @staticmethod
    def _select_supported_versions(
        configuration: OpenApiVersionDocsConfig,
        path: str,
        method: str,
    ) -> tuple[str, ...]:
        for override in configuration.operation_versions:
            if override.path == path and override.method == method:
                return override.supported_versions
        return configuration.supported_versions

    @staticmethod
    def _is_operation_suppressed(
        configuration: OpenApiVersionDocsConfig,
        path: str,
        method: str,
    ) -> bool:
        return any(
            selector.path == path and selector.method == method for selector in configuration.suppressed_operations
        )

    @staticmethod
    def _build_accept_versioning_extension(
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

    @staticmethod
    def _append_version_documentation(
        description: str | None,
        configuration: OpenApiVersionDocsConfig,
        supported_versions: tuple[str, ...],
    ) -> str:
        media_types: typing.Final = tuple(
            f"{configuration.vendor_media_type}; version={version}" for version in supported_versions
        )
        version_documentation: typing.Final = (
            f"Supported API version: `{media_types[0]}`."
            if len(media_types) == 1
            else "Supported API versions:\n" + "\n".join(f"- `{media_type}`." for media_type in media_types)
        )
        if not description:
            return version_documentation
        if version_documentation in description:
            return description
        return f"{description}\n\n{version_documentation}"

    @staticmethod
    def _validate_accept_versioning_extension(
        existing_extension: object,
        expected_extension: dict[str, str | list[str]],
        *,
        has_existing_extension: bool,
    ) -> None:
        if has_existing_extension and existing_extension != expected_extension:
            message = "OpenAPI operation x-accept-versioning conflicts with configured Accept version documentation."
            raise ValueError(message)

    def _expected_security_schemes(self) -> dict[str, dict[str, typing.Any]]:
        return serialize_security_schemes(self.instrument_config.security_schemes)

    def _validate_security_scheme_conflicts(self, existing_schemes: typing.Mapping[str, object]) -> None:
        for scheme_name, expected_scheme in self._expected_security_schemes().items():
            if scheme_name in existing_schemes and existing_schemes[scheme_name] != expected_scheme:
                message = f"OpenAPI security scheme '{scheme_name}' conflicts with the configured security scheme."
                raise ValueError(message)

    @classmethod
    def get_config_type(cls) -> type[SwaggerConfig]:
        return SwaggerConfig
