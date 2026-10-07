import typing
from unittest.mock import patch

import litestar
import pytest
from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol
from litestar.plugins.opentelemetry import OpenTelemetryPlugin
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND
from litestar.testing import TestClient
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import (
    LitestarBootstrapper,
    LitestarOpentelemetryInstrument,
    LitestarOpentelemetryRouteMiddleware,
    build_litestar_route_details_from_scope,
)
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    for environment_variable in ("OTEL_PYTHON_LITESTAR_EXCLUDED_URLS", "OTEL_PYTHON_EXCLUDED_URLS"):
        monkeypatch.delenv(environment_variable, raising=False)
    exporter: typing.Final = InMemorySpanExporter()

    def build_tracer_provider(*args: typing.Any, **kwargs: typing.Any) -> SdkTracerProvider:  # noqa: ANN401
        tracer_provider: typing.Final = SdkTracerProvider(*args, **kwargs)
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        return tracer_provider

    monkeypatch.setattr(opentelemetry_instrument, "SdkTracerProvider", build_tracer_provider)
    return exporter


def server_span_names(span_exporter: InMemorySpanExporter) -> list[str]:
    return [span.name for span in span_exporter.get_finished_spans() if span.kind == SpanKind.SERVER]


@pytest.mark.parametrize(
    ("scope", "expected_span_name", "expected_attributes"),
    [
        (
            {
                "path": "/users/123",
                "path_template": "/users/{user_id}",
                "method": "GET",
            },
            "GET /users/{user_id}",
            {"http.route": "/users/{user_id}"},
        ),
        (
            {
                "path": "/users/123",
                "method": "POST",
            },
            "POST /users/123",
            {"http.route": "/users/123"},
        ),
        (
            {
                "path": "/test",
            },
            "HTTP /test",
            {"http.route": "/test"},
        ),
        (
            {
                "path": "",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path": " ",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path_template": "",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path_template": " ",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {},
            "HTTP",
            {},
        ),
        (
            {"method": "GET"},
            "GET",
            {},
        ),
        (
            {
                "path": "/users/123",
                "path_template": "/users/{user_id}",
            },
            "HTTP /users/{user_id}",
            {"http.route": "/users/{user_id}"},
        ),
    ],
)
def test_build_litestar_route_details_from_scope(
    scope: dict[str, str],
    expected_span_name: str,
    expected_attributes: dict[str, str],
) -> None:
    span_name, attributes = build_litestar_route_details_from_scope(scope)  # type: ignore[arg-type]

    assert span_name == expected_span_name
    assert attributes == expected_attributes


def test_litestar_opentelemetry_instrument_uses_litestar_plugin(
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    minimal_opentelemetry_config.opentelemetry_exclude_urls = ["/metrics"]
    minimal_opentelemetry_config.opentelemetry_generate_health_check_spans = False
    minimal_opentelemetry_config.health_checks_path = "/health/"
    opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)
    opentelemetry_instrument.bootstrap()

    bootstrap_result: typing.Final = opentelemetry_instrument.bootstrap_before()

    assert [type(middleware) for middleware in bootstrap_result["middleware"]] == [LitestarOpentelemetryRouteMiddleware]
    assert len(bootstrap_result["plugins"]) == 1
    plugin: typing.Final = bootstrap_result["plugins"][0]
    assert isinstance(plugin, OpenTelemetryPlugin)
    assert plugin.config.tracer_provider is opentelemetry_instrument.tracer_provider
    assert plugin.config.scope_span_details_extractor is build_litestar_route_details_from_scope
    assert plugin.config.exclude == ["/metrics", "/health/"]


def test_litestar_opentelemetry_instrument_does_not_exclude_anything_by_default(
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    minimal_opentelemetry_config.opentelemetry_exclude_urls = []
    minimal_opentelemetry_config.opentelemetry_generate_health_check_spans = True
    opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)
    opentelemetry_instrument.bootstrap()

    plugin: typing.Final = opentelemetry_instrument.bootstrap_before()["plugins"][0]

    # An empty list must not be passed: Litestar would compile it into a pattern that matches every path
    assert plugin.config.exclude is None


@pytest.mark.parametrize(
    ("path", "expected_span_name", "expected_path_template"),
    [
        ("/users/123", "GET /users/{user_id}", "/users/{user_id}"),
        ("/users/", "GET /users/", "/users"),
        ("/", "GET /", "/"),
    ],
)
def test_litestar_opentelemetry_integration_with_path_templates(
    path: str,
    expected_span_name: str,
    expected_path_template: str,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    @litestar.get("/users/{user_id:int}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"user_id": user_id}

    @litestar.get("/users/")
    async def list_users() -> dict[str, str]:
        return {"message": "list of users"}

    @litestar.get("/")
    async def root() -> dict[str, str]:
        return {"message": "root"}

    with patch("microbootstrap.bootstrappers.litestar.build_litestar_route_details_from_scope") as mock_function:
        mock_function.return_value = (expected_span_name, {"http.route": path})

        application: typing.Final = (
            LitestarBootstrapper(LitestarSettings())
            .configure_instrument(minimal_opentelemetry_config)
            .configure_application(LitestarConfig(route_handlers=[get_user, list_users, root]))
            .bootstrap()
        )

        with TestClient(app=application) as client:
            response: typing.Final = client.get(path)
        assert response.status_code == HTTP_200_OK
        assert mock_function.called
        assert mock_function.call_args_list[0].args[0].get("path_template") == expected_path_template


def test_litestar_opentelemetry_server_spans_use_path_template(
    span_exporter: InMemorySpanExporter,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    @litestar.get("/users/{user_id:int}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"user_id": user_id}

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_instrument(minimal_opentelemetry_config)
        .configure_application(LitestarConfig(route_handlers=[get_user]))
        .bootstrap()
    )

    with TestClient(app=application) as client:
        assert client.get("/users/123").status_code == HTTP_200_OK

        assert client.get("/missing").status_code == HTTP_404_NOT_FOUND

    server_spans: typing.Final = [span for span in span_exporter.get_finished_spans() if span.kind == SpanKind.SERVER]
    assert [span.name for span in server_spans] == ["GET /users/{user_id}", "GET /missing"]
    assert server_spans[0].attributes is not None
    assert server_spans[0].attributes["http.route"] == "/users/{user_id}"
    assert server_spans[0].attributes["http.status_code"] == HTTP_200_OK


def test_litestar_opentelemetry_keeps_user_plugins(
    span_exporter: InMemorySpanExporter,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    class UserPlugin(InitPluginProtocol):
        def on_app_init(self, app_config: AppConfig) -> AppConfig:
            return app_config

    @litestar.get("/public")
    async def public() -> None: ...

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_instrument(minimal_opentelemetry_config)
        .configure_application(LitestarConfig(route_handlers=[public], plugins=[UserPlugin()]))
        .bootstrap()
    )

    assert any(isinstance(plugin, UserPlugin) for plugin in application.plugins.init)
    assert any(isinstance(plugin, OpenTelemetryPlugin) for plugin in application.plugins.init)
    with TestClient(app=application) as client:
        client.get("/public")
    assert server_span_names(span_exporter) == ["GET /public"]


def test_litestar_opentelemetry_excludes_urls_from_settings(
    span_exporter: InMemorySpanExporter,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    minimal_opentelemetry_config.opentelemetry_exclude_urls = ["/internal"]

    @litestar.get("/internal")
    async def internal() -> None: ...

    @litestar.get("/public")
    async def public() -> None: ...

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_instrument(minimal_opentelemetry_config)
        .configure_application(LitestarConfig(route_handlers=[internal, public]))
        .bootstrap()
    )

    with TestClient(app=application) as client:
        client.get("/internal")
        assert not span_exporter.get_finished_spans()

        client.get("/public")
    assert server_span_names(span_exporter) == ["GET /public"]


def test_litestar_opentelemetry_excludes_urls_from_environment(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    monkeypatch.setenv("OTEL_PYTHON_LITESTAR_EXCLUDED_URLS", "/from-env")
    minimal_opentelemetry_config.opentelemetry_exclude_urls = ["/from-settings"]

    @litestar.get("/from-env")
    async def from_env() -> None: ...

    @litestar.get("/from-settings")
    async def from_settings() -> None: ...

    @litestar.get("/other")
    async def other() -> None: ...

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_instrument(minimal_opentelemetry_config)
        .configure_application(LitestarConfig(route_handlers=[from_env, from_settings, other]))
        .bootstrap()
    )

    with TestClient(app=application) as client:
        client.get("/from-env")
        client.get("/from-settings")
        assert not span_exporter.get_finished_spans()

        client.get("/other")
    assert server_span_names(span_exporter) == ["GET /other"]
