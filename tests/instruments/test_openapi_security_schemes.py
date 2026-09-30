import typing

import pytest
from pydantic import ValidationError

from microbootstrap import OpenApiApiKeySecurityScheme as ApiKeySecurityScheme
from microbootstrap import (
    OpenApiHttpSecurityScheme,
    OpenApiOAuth2SecurityScheme,
    OpenApiOAuthFlow,
    OpenApiOAuthFlows,
    OpenApiOpenIdConnectSecurityScheme,
    OpenApiSecurityScheme,
    SwaggerConfig,
)
from microbootstrap.instruments.openapi_security_schemes import serialize_security_schemes


def test_security_schemes_accept_python_names_and_serialize_openapi_aliases() -> None:
    security_schemes: typing.Final[dict[str, OpenApiSecurityScheme]] = {
        "http.auth": OpenApiHttpSecurityScheme(scheme="bearer", bearer_format="JWT"),
        "api-key": ApiKeySecurityScheme(name="X-API-Key", location="header"),
        "oauth2": OpenApiOAuth2SecurityScheme(
            flows=OpenApiOAuthFlows(
                implicit=OpenApiOAuthFlow(authorization_url="/authorize", scopes={"read": "Read access"}),
                resource_owner=OpenApiOAuthFlow(token_url="/token", scopes={"write": "Write access"}),  # noqa: S106
                client_credentials=OpenApiOAuthFlow(token_url="/client-token"),  # noqa: S106
                authorization_code=OpenApiOAuthFlow(
                    authorization_url="/code-authorize",
                    token_url="/code-token",  # noqa: S106
                    refresh_url="/refresh",
                ),
            )
        ),
        "oidc": OpenApiOpenIdConnectSecurityScheme(open_id_connect_url="/.well-known/openid-configuration"),
    }

    assert serialize_security_schemes(security_schemes) == {
        "http.auth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "api-key": {"type": "apiKey", "name": "X-API-Key", "in": "header"},
        "oauth2": {
            "type": "oauth2",
            "flows": {
                "implicit": {"authorizationUrl": "/authorize", "scopes": {"read": "Read access"}},
                "password": {"tokenUrl": "/token", "scopes": {"write": "Write access"}},
                "clientCredentials": {"tokenUrl": "/client-token", "scopes": {}},
                "authorizationCode": {
                    "authorizationUrl": "/code-authorize",
                    "tokenUrl": "/code-token",
                    "refreshUrl": "/refresh",
                    "scopes": {},
                },
            },
        },
        "oidc": {"type": "openIdConnect", "openIdConnectUrl": "/.well-known/openid-configuration"},
    }


def test_security_schemes_accept_openapi_aliases() -> None:
    configuration: typing.Final = SwaggerConfig(
        security_schemes={
            "api": {"type": "apiKey", "name": "X-API-Key", "in": "query"},
            "oauth": {
                "type": "oauth2",
                "flows": {"clientCredentials": {"tokenUrl": "relative-token", "scopes": {}}},
            },
            "oidc": {"type": "openIdConnect", "openIdConnectUrl": "relative-discovery"},
        }
    )

    assert serialize_security_schemes(configuration.security_schemes) == {
        "api": {"type": "apiKey", "name": "X-API-Key", "in": "query"},
        "oauth": {
            "type": "oauth2",
            "flows": {"clientCredentials": {"tokenUrl": "relative-token", "scopes": {}}},
        },
        "oidc": {"type": "openIdConnect", "openIdConnectUrl": "relative-discovery"},
    }


def test_oauth_flows_accept_python_and_openapi_password_names() -> None:
    flow: typing.Final = OpenApiOAuthFlow(token_url="/token")  # noqa: S106
    flows: typing.Final = OpenApiOAuthFlows(resource_owner=flow)
    flow_arguments: typing.Final = {"password": flow}
    alias_flows: typing.Final = OpenApiOAuthFlows(**flow_arguments)

    assert flows.resource_owner == alias_flows.resource_owner == flow


@pytest.mark.parametrize(
    ("flows", "error"),
    [
        ({"implicit": {"scopes": {}}}, "implicit flow requires authorizationUrl"),
        ({"password": {"scopes": {}}}, "password flow requires tokenUrl"),
        ({"clientCredentials": {"scopes": {}}}, "client credentials flow requires tokenUrl"),
        (
            {"authorizationCode": {"tokenUrl": "/token", "scopes": {}}},
            "authorization code flow requires authorizationUrl",
        ),
        (
            {"authorizationCode": {"authorizationUrl": "/authorize", "scopes": {}}},
            "authorization code flow requires tokenUrl",
        ),
    ],
)
def test_oauth_flows_require_urls_for_configured_grant_types(flows: dict[str, object], error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        OpenApiOAuthFlows.model_validate(flows)


def test_oauth_flows_require_at_least_one_grant_type() -> None:
    with pytest.raises(ValidationError, match="must configure at least one grant type"):
        OpenApiOAuthFlows()


@pytest.mark.parametrize("url", ["", " ", "/oauth token", "/oauth\ttoken", "/oauth\ntoken", "/oauth\x00token"])
def test_oauth_and_openid_urls_reject_empty_whitespace_and_control_characters(url: str) -> None:
    with pytest.raises(ValidationError, match="must be non-empty"):
        OpenApiOAuthFlow(token_url=url)
    with pytest.raises(ValidationError, match="must be non-empty"):
        OpenApiOpenIdConnectSecurityScheme(open_id_connect_url=url)


def test_oauth_and_openid_urls_allow_relative_references() -> None:
    flow: typing.Final = OpenApiOAuthFlow(
        authorization_url="authorize",
        token_url="../token",  # noqa: S106 - a relative URL is under test.
        refresh_url="./refresh",
    )
    oidc: typing.Final = OpenApiOpenIdConnectSecurityScheme(open_id_connect_url=".well-known/openid-configuration")

    assert flow.authorization_url == "authorize"
    assert flow.token_url == "../token"  # noqa: S105 - a relative URL is under test.
    assert flow.refresh_url == "./refresh"
    assert oidc.open_id_connect_url == ".well-known/openid-configuration"


@pytest.mark.parametrize(
    "configuration",
    [
        lambda: OpenApiHttpSecurityScheme.model_validate({"scheme": "bearer", "unexpected": "value"}),
        lambda: ApiKeySecurityScheme.model_validate({"name": "X-API-Key", "location": "header", "unexpected": "value"}),
        lambda: OpenApiOAuthFlow.model_validate({"tokenUrl": "/token", "unexpected": "value"}),
        lambda: OpenApiOAuthFlows.model_validate({"clientCredentials": {"tokenUrl": "/token"}, "unexpected": "value"}),
        lambda: OpenApiOAuth2SecurityScheme.model_validate({"flows": {}, "unexpected": "value"}),
        lambda: OpenApiOpenIdConnectSecurityScheme.model_validate(
            {"openIdConnectUrl": "/discovery", "unexpected": "value"}
        ),
    ],
)
def test_security_scheme_models_forbid_unknown_fields(configuration: typing.Callable[[], object]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        configuration()


@pytest.mark.parametrize("scheme_name", ["", "service auth", "service/auth", "служебная"])
def test_security_scheme_component_names_must_match_openapi_pattern(scheme_name: str) -> None:
    with pytest.raises(ValidationError, match=r"\^\[a-zA-Z0-9\._-\]\+\$"):
        SwaggerConfig(security_schemes={scheme_name: OpenApiHttpSecurityScheme(scheme="bearer")})


def test_security_scheme_component_names_allow_openapi_non_identifiers() -> None:
    configuration: typing.Final = SwaggerConfig(
        security_schemes={"service.auth-1": OpenApiHttpSecurityScheme(scheme="bearer")}
    )

    assert set(configuration.security_schemes) == {"service.auth-1"}
