import typing
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig
from microbootstrap.settings import FastApiSettings


def test_fastapi_configure_instrument() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instrument(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_fastapi_configure_instruments() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instruments(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_fastapi_configure_application() -> None:
    test_title: typing.Final = "new-title"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings()).configure_application(FastApiConfig(title=test_title)).bootstrap()
    )

    assert application.title == test_title


def test_fastapi_configure_application_lifespan(magic_mock: MagicMock) -> None:
    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings()).configure_application(FastApiConfig(lifespan=magic_mock)).bootstrap()
    )

    with TestClient(app=application):
        assert magic_mock.called


def test_fastapi_configure_application_openapi_and_documentation_options() -> None:
    class Widget(BaseModel):
        name: str
        generated: str = "server-default"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings(service_debug=False))
        .configure_application(
            FastApiConfig(
                title="Widgets API",
                summary="Widget contract",
                description="Configure widgets",
                version="1.0.0",
                openapi_url="/widget-schema.json",
                docs_url="/widget-docs",
                redoc_url="/widget-redoc",
                separate_input_output_schemas=False,
            )
        )
        .bootstrap()
    )

    @application.post("/widgets", response_model=Widget)
    async def create_widget(widget: Widget) -> Widget:
        return widget

    with TestClient(app=application) as test_client:
        schema_response: typing.Final = test_client.get("/widget-schema.json")
        swagger_response: typing.Final = test_client.get("/widget-docs")
        redoc_response: typing.Final = test_client.get("/widget-redoc")

    assert schema_response.status_code == status.HTTP_200_OK
    assert schema_response.json()["info"] == {
        "title": "Widgets API",
        "summary": "Widget contract",
        "description": "Configure widgets",
        "version": "1.0.0",
    }
    assert (
        schema_response.json()["components"]["schemas"]["Widget"]["properties"]["generated"]["default"]
        == "server-default"
    )
    assert application.separate_input_output_schemas is False
    assert swagger_response.status_code == status.HTTP_200_OK
    assert "/widget-schema.json" in swagger_response.text
    assert redoc_response.status_code == status.HTTP_200_OK
    assert "/widget-schema.json" in redoc_response.text
