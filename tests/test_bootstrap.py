from __future__ import annotations
import logging
import typing

import fastapi.testclient
import litestar
import litestar.testing
from granian.log import LogLevels
from litestar.handlers.http_handlers.base import HTTPRouteHandler  # noqa: TCH002
from litestar.status_codes import HTTP_200_OK
from starlette import status

from microbootstrap import granian_server
from microbootstrap.base.base import BootstrapServicesBootstrapper
from microbootstrap.bootstrappers.fastapi import FastAPIBootstrapper
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from tests import settings_for_test


if typing.TYPE_CHECKING:
    import pytest
    from fastapi import FastAPI


def test_bootstrap__fastapi__bootstrap_and_teardown(
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ci_commit_tag", "2.0.0")
    monkeypatch.setenv("bootstrap_namespace", "newhost")
    monkeypatch.setenv("bootstrap_sentry_dsn", "https://testdsn@test.sentry.com/1")
    monkeypatch.setenv("bootstrap_enable_prometheus_instrumentator", "true")
    monkeypatch.setenv("bootstrap_prometheus_instrumentator_params", '{"should_round_latency_decimals": true}')

    bootstrap_settings = settings_for_test.TestFastAPIBootstrapSettings()
    app_init_params = granian_server.bootstrap(
        web_framework=FastAPIBootstrapper,
        settings=bootstrap_settings,
        app=fastapi_app,
    )
    assert app_init_params is None

    response: typing.Final = fastapi.testclient.TestClient(fastapi_app).get("/test")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == default_response_content

    granian_server.teardown(
        web_framework=FastAPIBootstrapper,
        settings=bootstrap_settings,
        app=fastapi_app,
    )


def test_bootstrap__fastapi__teardown_only(
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
) -> None:
    granian_server.teardown(
        web_framework=FastAPIBootstrapper,
        settings=settings_for_test.TestFastAPIBootstrapSettings(),
        app=fastapi_app,
    )

    response: typing.Final = fastapi.testclient.TestClient(fastapi_app).get("/test")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == default_response_content


def test_bootstrap__litestar__bootstrap_and_teardown(
    test_litestar_endpoint: HTTPRouteHandler,
    health_litestar_endpoint: HTTPRouteHandler,
    default_response_content: "dict[str, str]",  # noqa: UP037
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ci_commit_tag", "2.0.0")
    monkeypatch.setenv("bootstrap_namespace", "new_host")
    monkeypatch.setenv("bootstrap_sentry_dsn", "https://testdsn@test.sentry.com/1")
    monkeypatch.setenv("bootstrap_static_path", "/static-files")

    bootstrap_settings: typing.Final = settings_for_test.TestLitestarBootstrapSettings()
    app_config: typing.Final = granian_server.bootstrap(
        web_framework=LitestarBootstrapper,
        settings=bootstrap_settings,
        app=None,
    )
    app_config.route_handlers += [test_litestar_endpoint, health_litestar_endpoint]
    litestar_application: typing.Final = litestar.Litestar.from_config(app_config)
    with litestar.testing.TestClient(app=litestar_application) as test_litestar_client:
        response: typing.Final = test_litestar_client.get("/test")
        assert response.status_code == HTTP_200_OK
        assert response.json() == default_response_content

    granian_server.teardown(web_framework=LitestarBootstrapper, settings=bootstrap_settings, app=None)


def test_bootstrap__litestar__teardown_only(
    test_litestar_endpoint: HTTPRouteHandler,
    health_litestar_endpoint: HTTPRouteHandler,
    default_response_content: dict[str, str],
) -> None:
    granian_server.teardown(
        web_framework=LitestarBootstrapper,
        settings=settings_for_test.TestLitestarBootstrapSettings(),
        app=None,
    )
    litestar_application: typing.Final = litestar.Litestar(
        route_handlers=[test_litestar_endpoint, health_litestar_endpoint],
    )

    with litestar.testing.TestClient(app=litestar_application) as test_litestar_client:
        response: typing.Final = test_litestar_client.get("/test")
        assert response.status_code == HTTP_200_OK
        assert response.json() == default_response_content


def test_bootstrap_enter_bootstrapper_context() -> None:
    class TestingBootstrapper(BootstrapServicesBootstrapper[settings_for_test.TestBootstrapSettings]):
        load_parameters_calls: typing.ClassVar[int]
        initialize_calls: typing.ClassVar[int]
        teardown_calls: typing.ClassVar[int]

    def create_bootstrapper_class() -> type[TestingBootstrapper]:
        class CurrentBootstrapper(TestingBootstrapper):
            load_parameters_calls = 0
            initialize_calls = 0
            teardown_calls = 0

            def load_parameters(self, settings: settings_for_test.TestBootstrapSettings | None = None) -> None:
                CurrentBootstrapper.load_parameters_calls += 1
                assert settings is expected_settings

            def initialize(self) -> None:
                CurrentBootstrapper.initialize_calls += 1

            def teardown(self) -> None:
                CurrentBootstrapper.teardown_calls += 1

        return CurrentBootstrapper

    classes: typing.Final = [create_bootstrapper_class() for _ in range(10)]
    expected_settings: typing.Final = settings_for_test.TestBootstrapSettings()

    with granian_server.enter_bootstrapper_context(*classes, settings=expected_settings):
        for one_class in classes:
            assert one_class.load_parameters_calls == 1
            assert one_class.initialize_calls == 1
            assert one_class.teardown_calls == 0

    for one_class in classes:
        assert one_class.teardown_calls == 1


def test_create_granian_server() -> None:
    target: typing.Final = "mytarget"
    settings: typing.Final = settings_for_test.TestFastAPIBootstrapSettings(logging_log_level=logging.CRITICAL)
    process_name: typing.Final = "myprocess"

    server: typing.Final = granian_server.create_granian_server(target, settings, process_name=process_name)
    assert server.target == target
    assert server.bind_addr == settings.server_host
    assert server.bind_port == settings.server_port
    assert server.workers == settings.server_workers_count
    assert server.log_level == LogLevels.critical
    assert server.reload_on_changes == settings.server_reload
    assert server.process_name == process_name
