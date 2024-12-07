import typing

import fastapi
import litestar
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from litestar.config.cors import CORSConfig as LitestarCorsConfig

from microbootstrap import CorsConfig
from microbootstrap.bootstrappers.fastapi import FastApiCorsInstrument
from microbootstrap.bootstrappers.litestar import LitestarCorsInstrument
from microbootstrap.instruments.cors_instrument import CorsInstrument


def test_cors_is_ready(minimal_cors_config: CorsConfig) -> None:
    cors_instrument: typing.Final = CorsInstrument(minimal_cors_config)
    assert cors_instrument.is_ready()


def test_cors_bootstrap_is_not_ready(minimal_cors_config: CorsConfig) -> None:
    minimal_cors_config.cors_allowed_origins = []
    cors_instrument: typing.Final = CorsInstrument(minimal_cors_config)
    assert not cors_instrument.is_ready()


def test_cors_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_cors_config: CorsConfig,
) -> None:
    cors_instrument: typing.Final = CorsInstrument(minimal_cors_config)
    assert cors_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_cors_teardown(
    minimal_cors_config: CorsConfig,
) -> None:
    cors_instrument: typing.Final = CorsInstrument(minimal_cors_config)
    assert cors_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_cors_bootstrap() -> None:
    cors_config = CorsConfig(
        cors_allowed_origins=["localhost"],
        cors_allowed_headers=["my-allowed-header"],
        cors_allowed_credentials=True,
        cors_allowed_origin_regex="my-regex",
        cors_allowed_methods=["*"],
        cors_exposed_headers=["my-exposed-header"],
        cors_max_age=100,
    )
    cors_instrument: typing.Final = LitestarCorsInstrument(cors_config)

    cors_instrument.bootstrap()
    bootstrap_result: typing.Final = cors_instrument.bootstrap_before()
    assert "cors_config" in bootstrap_result
    assert isinstance(bootstrap_result["cors_config"], LitestarCorsConfig)
    assert bootstrap_result["cors_config"].allow_origins == cors_config.cors_allowed_origins
    assert bootstrap_result["cors_config"].allow_headers == cors_config.cors_allowed_headers
    assert bootstrap_result["cors_config"].allow_credentials == cors_config.cors_allowed_credentials
    assert bootstrap_result["cors_config"].allow_origin_regex == cors_config.cors_allowed_origin_regex
    assert bootstrap_result["cors_config"].allow_methods == cors_config.cors_allowed_methods
    assert bootstrap_result["cors_config"].expose_headers == cors_config.cors_exposed_headers
    assert bootstrap_result["cors_config"].max_age == cors_config.cors_max_age


def test_fastapi_cors_bootstrap() -> None:
    cors_config = CorsConfig(
        cors_allowed_origins=["localhost"],
        cors_allowed_headers=["my-allowed-header"],
        cors_allowed_credentials=True,
        cors_allowed_origin_regex="my-regex",
        cors_allowed_methods=["*"],
        cors_exposed_headers=["my-exposed-header"],
        cors_max_age=100,
    )
    cors_instrument: typing.Final = FastApiCorsInstrument(cors_config)
    fastapi_application = cors_instrument.bootstrap_after(fastapi.FastAPI())
    assert len(fastapi_application.user_middleware) == 1
    assert isinstance(fastapi_application.user_middleware[0], Middleware)
    cors_middleware: typing.Final = fastapi_application.user_middleware[0]
    assert cors_middleware.cls is CORSMiddleware  # type: ignore[comparison-overlap]
    assert cors_middleware.kwargs["allow_origins"] == cors_config.cors_allowed_origins
    assert cors_middleware.kwargs["allow_headers"] == cors_config.cors_allowed_headers
    assert cors_middleware.kwargs["allow_credentials"] == cors_config.cors_allowed_credentials
    assert cors_middleware.kwargs["allow_origin_regex"] == cors_config.cors_allowed_origin_regex
    assert cors_middleware.kwargs["allow_methods"] == cors_config.cors_allowed_methods
    assert cors_middleware.kwargs["expose_headers"] == cors_config.cors_exposed_headers
    assert cors_middleware.kwargs["max_age"] == cors_config.cors_max_age
