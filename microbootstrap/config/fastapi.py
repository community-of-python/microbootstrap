from __future__ import annotations
import dataclasses
import typing

from fastapi.datastructures import Default
from fastapi.utils import generate_unique_id
from starlette.responses import JSONResponse


if typing.TYPE_CHECKING:
    from fastapi import Request, routing
    from fastapi.applications import AppType
    from fastapi.middleware import Middleware
    from fastapi.params import Depends
    from starlette.responses import Response
    from starlette.routing import BaseRoute
    from starlette.types import Lifespan


@dataclasses.dataclass
class FastApiConfig:
    debug: bool = False
    routes: list[BaseRoute] | None = None
    title: str = "FastAPI"
    summary: str | None = None
    description: str = ""
    version: str = "0.1.0"
    openapi_url: str | None = "/openapi.json"
    openapi_tags: list[dict[str, typing.Any]] | None = None
    servers: list[dict[str, str | typing.Any]] | None = None
    dependencies: typing.Sequence[Depends] | None = None
    default_response_class: type[Response] = dataclasses.field(default_factory=lambda: Default(JSONResponse))
    redirect_slashes: bool = True
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    swagger_ui_oauth2_redirect_url: str | None = "/docs/oauth2-redirect"
    swagger_ui_init_oauth: dict[str, typing.Any] | None = None
    middleware: typing.Sequence[Middleware] | None = None
    exception_handlers: (
        dict[
            int | type[Exception],
            typing.Callable[[Request, typing.Any], typing.Coroutine[typing.Any, typing.Any, Response]],
        ]
        | None
    ) = None
    on_startup: typing.Sequence[typing.Callable[[], typing.Any]] | None = None
    on_shutdown: typing.Sequence[typing.Callable[[], typing.Any]] | None = None
    lifespan: Lifespan[AppType] | None = None  # type: ignore[valid-type]
    terms_of_service: str | None = None
    contact: dict[str, str | typing.Any] | None = None
    license_info: dict[str, str | typing.Any] | None = None
    openapi_prefix: str = ""
    root_path: str = ""
    root_path_in_servers: bool = True
    responses: dict[int | str, dict[str, typing.Any]] | None = None
    callbacks: list[BaseRoute] | None = None
    webhooks: routing.APIRouter | None = None
    deprecated: bool | None = None
    include_in_schema: bool = True
    swagger_ui_parameters: dict[str, typing.Any] | None = None
    generate_unique_id_function: typing.Callable[[routing.APIRoute], str] = dataclasses.field(
        default_factory=lambda: Default(generate_unique_id),
    )
    separate_input_output_schemas: bool = True
