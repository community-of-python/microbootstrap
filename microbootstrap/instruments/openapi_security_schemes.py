from __future__ import annotations
import typing
import unicodedata

import pydantic


OpenApiApiKeyLocation: typing.TypeAlias = typing.Literal["header", "query", "cookie"]


class OpenApiSecuritySchemeModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid", populate_by_name=True)


class OpenApiHttpSecurityScheme(OpenApiSecuritySchemeModel):
    type: typing.Literal["http"] = "http"
    scheme: str
    bearer_format: str | None = pydantic.Field(default=None, alias="bearerFormat")
    description: str | None = None


class OpenApiApiKeySecurityScheme(OpenApiSecuritySchemeModel):
    type: typing.Literal["apiKey"] = "apiKey"
    name: str
    location: OpenApiApiKeyLocation = pydantic.Field(alias="in")
    description: str | None = None


class OpenApiOAuthFlow(OpenApiSecuritySchemeModel):
    authorization_url: str | None = pydantic.Field(default=None, alias="authorizationUrl")
    token_url: str | None = pydantic.Field(default=None, alias="tokenUrl")
    refresh_url: str | None = pydantic.Field(default=None, alias="refreshUrl")
    scopes: dict[str, str] = pydantic.Field(default_factory=dict)

    @pydantic.field_validator("authorization_url", "token_url", "refresh_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return validate_openapi_url(value)


class OpenApiOAuthFlows(OpenApiSecuritySchemeModel):
    implicit: OpenApiOAuthFlow | None = None
    resource_owner: OpenApiOAuthFlow | None = pydantic.Field(default=None, alias="password")
    client_credentials: OpenApiOAuthFlow | None = pydantic.Field(default=None, alias="clientCredentials")
    authorization_code: OpenApiOAuthFlow | None = pydantic.Field(default=None, alias="authorizationCode")

    @pydantic.model_validator(mode="after")
    def validate_required_urls(self) -> OpenApiOAuthFlows:
        if all(
            flow is None
            for flow in (self.implicit, self.resource_owner, self.client_credentials, self.authorization_code)
        ):
            message = "OAuth2 flows must configure at least one grant type."
            raise ValueError(message)
        self._validate_flow_urls("implicit", self.implicit, requires_authorization_url=True)
        self._validate_flow_urls("password", self.resource_owner, requires_token_url=True)
        self._validate_flow_urls("client credentials", self.client_credentials, requires_token_url=True)
        self._validate_flow_urls(
            "authorization code",
            self.authorization_code,
            requires_authorization_url=True,
            requires_token_url=True,
        )
        return self

    @staticmethod
    def _validate_flow_urls(
        flow_name: str,
        flow: OpenApiOAuthFlow | None,
        *,
        requires_authorization_url: bool = False,
        requires_token_url: bool = False,
    ) -> None:
        if flow is None:
            return
        if requires_authorization_url and flow.authorization_url is None:
            message = f"OAuth2 {flow_name} flow requires authorizationUrl."
            raise ValueError(message)
        if requires_token_url and flow.token_url is None:
            message = f"OAuth2 {flow_name} flow requires tokenUrl."
            raise ValueError(message)


class OpenApiOAuth2SecurityScheme(OpenApiSecuritySchemeModel):
    type: typing.Literal["oauth2"] = "oauth2"
    flows: OpenApiOAuthFlows
    description: str | None = None


class OpenApiOpenIdConnectSecurityScheme(OpenApiSecuritySchemeModel):
    type: typing.Literal["openIdConnect"] = "openIdConnect"
    open_id_connect_url: str = pydantic.Field(alias="openIdConnectUrl")
    description: str | None = None

    @pydantic.field_validator("open_id_connect_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        validated_value = validate_openapi_url(value)
        assert validated_value is not None  # noqa: S101 - this field is required.
        return validated_value


_OpenApiSecurityScheme: typing.TypeAlias = typing.Annotated[
    OpenApiHttpSecurityScheme
    | OpenApiApiKeySecurityScheme
    | OpenApiOAuth2SecurityScheme
    | OpenApiOpenIdConnectSecurityScheme,
    pydantic.Field(discriminator="type"),
]


def validate_openapi_url(value: str | None) -> str | None:
    if value is None:
        return value
    if not value or any(character.isspace() or unicodedata.category(character) == "Cc" for character in value):
        message = "OpenAPI URL values must be non-empty and contain no whitespace or control characters."
        raise ValueError(message)
    return value


def serialize_security_schemes(
    security_schemes: typing.Mapping[str, _OpenApiSecurityScheme],
) -> dict[str, dict[str, typing.Any]]:
    return {
        scheme_name: security_scheme.model_dump(by_alias=True, exclude_none=True)
        for scheme_name, security_scheme in security_schemes.items()
    }
