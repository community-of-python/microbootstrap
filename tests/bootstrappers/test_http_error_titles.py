import http
import typing

import fastapi
import litestar
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from litestar.config.app import AppConfig
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.testing import TestClient as LitestarTestClient

from microbootstrap import FastApiSettings, HttpErrorTitlesConfig, LitestarSettings
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.config.litestar import LitestarConfig


if typing.TYPE_CHECKING:
    from litestar.types import ExceptionHandlersMap


NONSTANDARD_STATUS: typing.Final = 599


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("status_code", [http.HTTPStatus.BAD_REQUEST, http.HTTPStatus.UNAUTHORIZED, NONSTANDARD_STATUS])
def test_fastapi_errors_preserve_fields_headers_and_status(enabled: bool, status_code: int) -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(service_debug=False, http_error_titles_enabled=enabled)
    ).bootstrap()

    @application.get("/error")
    def reject() -> None:
        raise fastapi.HTTPException(
            status_code=status_code, detail={"reason": "rejected"}, headers={"X-Reason": "test"}
        )

    with FastAPITestClient(application) as client:
        response = client.get("/error")
    assert response.status_code == status_code
    assert response.headers["x-reason"] == "test"
    assert response.json()["detail"] == {"reason": "rejected"}
    assert ("title" in response.json()) is enabled
    if enabled:
        assert response.json()["title"] == (
            "HTTP error" if status_code == NONSTANDARD_STATUS else http.HTTPStatus(status_code).phrase
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_fastapi_validation_schema_matches_real_errors(enabled: bool) -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(service_debug=False, http_error_titles_enabled=enabled)
    ).bootstrap()

    @application.get("/items")
    def get_items(limit: int) -> int:
        return limit

    schema: typing.Final = application.openapi()
    assert application.openapi() == schema
    error: typing.Final = schema["components"]["schemas"]["HTTPValidationError"]
    assert ("title" in error.get("required", [])) is enabled
    assert ("title" in error["properties"]) is enabled
    with FastAPITestClient(application) as client:
        assert client.get("/items?limit=1").json() == 1
        response = client.get("/items?limit=invalid")
    assert response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert isinstance(response.json()["detail"], list)
    assert ("title" in response.json()) is enabled


def test_fastapi_empty_schema_and_non_error_exception_keep_native_behavior() -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(service_debug=False, http_error_titles_enabled=True, health_checks_enabled=False)
    ).bootstrap()
    assert not application.openapi().get("components", {}).get("schemas")

    @application.get("/redirect")
    def redirect() -> None:
        raise fastapi.HTTPException(status_code=http.HTTPStatus.NOT_MODIFIED, headers={"ETag": "test"})

    with FastAPITestClient(application) as client:
        response = client.get("/redirect")
    assert response.status_code == http.HTTPStatus.NOT_MODIFIED
    assert response.content == b""
    assert response.headers["etag"] == "test"


def test_fastapi_custom_validation_handler_keeps_ownership() -> None:
    async def custom_validation(_request: fastapi.Request, _exc: Exception) -> fastapi.responses.JSONResponse:
        return fastapi.responses.JSONResponse({"owned": True}, status_code=http.HTTPStatus.BAD_REQUEST)

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings(service_debug=False, http_error_titles_enabled=True))
        .configure_application(
            FastApiConfig(exception_handlers={fastapi.exceptions.RequestValidationError: custom_validation})
        )
        .bootstrap()
    )

    @application.get("/items")
    def get_items(limit: int) -> int:
        return limit

    assert "title" not in application.openapi()["components"]["schemas"]["HTTPValidationError"].get("required", [])
    with FastAPITestClient(application) as client:
        assert client.get("/items?limit=1").json() == 1
        assert client.get("/items?limit=invalid").json() == {"owned": True}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("media_type", [litestar.MediaType.JSON, litestar.MediaType.HTML])
def test_litestar_errors_preserve_fields_headers_and_status(enabled: bool, media_type: litestar.MediaType) -> None:
    @litestar.get("/error", sync_to_thread=False, media_type=media_type)
    def reject() -> None:
        raise LitestarHTTPException(
            status_code=http.HTTPStatus.UNAUTHORIZED,
            detail="rejected",
            extra={"reason": "test"},
            headers={"X-Reason": "test"},
        )

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(service_debug=False, http_error_titles_enabled=enabled))
        .configure_application(LitestarConfig(route_handlers=[reject]))
        .bootstrap()
    )
    with LitestarTestClient(application) as client:
        response = client.get("/error")
    assert response.status_code == http.HTTPStatus.UNAUTHORIZED
    assert response.headers["x-reason"] == "test"
    assert response.json()["detail"] == "rejected"
    assert response.json()["extra"] == {"reason": "test"}
    assert ("title" in response.json()) is enabled
    if enabled:
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["title"] == "Unauthorized"


@pytest.mark.parametrize("enabled", [False, True])
def test_litestar_validation_schema_matches_real_errors(enabled: bool) -> None:
    @litestar.get("/items", sync_to_thread=False)
    def get_items(limit: int) -> int:
        return limit

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(service_debug=False))
        .configure_instrument(HttpErrorTitlesConfig(http_error_titles_enabled=enabled))
        .configure_application(LitestarConfig(route_handlers=[get_items]))
        .bootstrap()
    )
    schema: typing.Final = application.openapi_schema.to_schema()
    error: typing.Final = schema["paths"]["/items"]["get"]["responses"]["400"]["content"]["application/json"]["schema"]
    assert ("title" in error["required"]) is enabled
    with LitestarTestClient(application) as client:
        assert client.get("/items?limit=1").json() == 1
        response = client.get("/items?limit=invalid")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert ("title" in response.json()) is enabled


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
def test_internal_errors_have_safe_titles(framework: str) -> None:
    def fail() -> None:
        raise RuntimeError("private diagnostic")

    if framework == "fastapi":
        application = FastApiBootstrapper(
            FastApiSettings(service_debug=False, http_error_titles_enabled=True)
        ).bootstrap()
        application.get("/error")(fail)
        with FastAPITestClient(application, raise_server_exceptions=False) as client:
            response = client.get("/error")
    else:
        handler: typing.Final = litestar.get("/error", sync_to_thread=False)(fail)
        litestar_application: typing.Final = (
            LitestarBootstrapper(LitestarSettings(service_debug=False, http_error_titles_enabled=True))
            .configure_application(LitestarConfig(route_handlers=[handler]))
            .bootstrap()
        )
        with LitestarTestClient(litestar_application, raise_server_exceptions=False) as litestar_client:
            response = litestar_client.get("/error")
    assert response.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["title"] == "Internal Server Error"
    assert "private diagnostic" not in response.text


def test_setting_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert HttpErrorTitlesConfig().http_error_titles_enabled is False
    monkeypatch.setenv("HTTP_ERROR_TITLES_ENABLED", "true")
    assert FastApiSettings().http_error_titles_enabled is True
    assert LitestarSettings().http_error_titles_enabled is True


@pytest.mark.parametrize("level", ["application", "controller", "router", "route"])
@pytest.mark.parametrize("key", [http.HTTPStatus.BAD_REQUEST, litestar.exceptions.ValidationException])
def test_litestar_custom_validation_handler_owns_payload_and_schema(level: str, key: int | type[Exception]) -> None:
    def custom_validation(
        _request: litestar.Request[typing.Any, typing.Any, typing.Any], _exc: Exception
    ) -> litestar.Response[typing.Any]:
        return litestar.Response({"status_code": 400, "detail": "owned", "extra": None}, status_code=400)

    handlers: typing.Final[ExceptionHandlersMap] = {key: custom_validation}

    @litestar.get("/items", sync_to_thread=False, exception_handlers=handlers if level == "route" else None)
    def get_items(limit: int) -> int:
        return limit

    class ItemsController(litestar.Controller):
        path = "/"
        exception_handlers = handlers if level == "controller" else None

        @litestar.get("/items", sync_to_thread=False)
        def items(self, limit: int) -> int:
            return limit

    router: typing.Final = litestar.Router(
        path="/",
        route_handlers=[ItemsController if level == "controller" else get_items],
        exception_handlers=handlers if level == "router" else None,
    )
    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(service_debug=False, http_error_titles_enabled=True))
        .configure_application(
            LitestarConfig(route_handlers=[router], exception_handlers=handlers if level == "application" else {})
        )
        .bootstrap()
    )
    error: typing.Final = application.openapi_schema.to_schema()["paths"]["/items"]["get"]["responses"]["400"][
        "content"
    ]["application/json"]["schema"]
    assert "title" not in error["required"]
    with LitestarTestClient(application) as client:
        response = client.get("/items?limit=invalid")
        assert client.get("/items?limit=1").json() == 1
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert response.json() == {"status_code": 400, "detail": "owned", "extra": None}


@pytest.mark.parametrize("enabled", [False, True])
def test_litestar_debug_traceback_remains_framework_owned(enabled: bool) -> None:
    @litestar.get("/error", sync_to_thread=False)
    def fail() -> None:
        raise RuntimeError("private diagnostic")

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings(service_debug=True, http_error_titles_enabled=enabled))
        .configure_application(LitestarConfig(route_handlers=[fail]))
        .bootstrap()
    )
    with LitestarTestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/error")
    assert response.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR
    assert "private diagnostic" in response.text
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize("swagger_enabled", [False, True])
def test_litestar_non_http_routes_and_combined_error_schemas(swagger_enabled: bool) -> None:
    @litestar.get(
        "/items",
        sync_to_thread=False,
        raises=[litestar.exceptions.ValidationException, litestar.exceptions.ClientException, LitestarHTTPException],
    )
    def get_items(limit: int) -> int:
        return limit

    @litestar.websocket("/ws")
    async def websocket_handler(socket: litestar.WebSocket[typing.Any, typing.Any, typing.Any]) -> None:
        await socket.accept()
        await socket.send_text("ready")
        await socket.close()

    def disable_docs(config: AppConfig) -> AppConfig:
        config.openapi_config = None
        return config

    application: typing.Final = (
        LitestarBootstrapper(
            LitestarSettings(service_debug=False, http_error_titles_enabled=True, swagger_enabled=swagger_enabled)
        )
        .configure_application(
            LitestarConfig(
                route_handlers=[get_items, websocket_handler], on_app_init=[] if swagger_enabled else [disable_docs]
            )
        )
        .bootstrap()
    )
    with LitestarTestClient(application) as client:
        with client.websocket_connect("/ws") as websocket:
            assert websocket.receive_text() == "ready"
        assert client.get("/items?limit=1").json() == 1
        response = client.get("/items?limit=invalid")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert response.json()["title"] == "Bad Request"
    if swagger_enabled:
        schema: typing.Final = application.openapi_schema.to_schema()["paths"]["/items"]["get"]["responses"]["400"][
            "content"
        ]["application/json"]["schema"]
        assert all("title" in branch["required"] for branch in schema["oneOf"])
        assert "500" in application.openapi_schema.to_schema()["paths"]["/items"]["get"]["responses"]
