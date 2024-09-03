import typing

import fastapi
import typing_extensions
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline_docs import enable_offline_docs
from sentry_sdk.integrations.fastapi import FastApiIntegration

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastapi import FastAPIConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
from microbootstrap.settings import FastApiSettings


class FastApiBootstrapper(
    ApplicationBootstrapper[FastApiSettings, fastapi.FastAPI, FastAPIConfig],
):
    application_config = FastAPIConfig()
    application_type = fastapi.FastAPI

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "debug": self.settings.service_debug,
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
        }


@FastApiBootstrapper.use_instrument()
class FastApiSentryInstrument(SentryInstrument):
    def bootstrap(self) -> None:
        for sentry_integration in self.instrument_config.sentry_integrations:
            if isinstance(sentry_integration, FastApiIntegration):
                break
        else:
            self.instrument_config.sentry_integrations.append(FastApiIntegration())
        super().bootstrap()


@FastApiBootstrapper.use_instrument()
class FastApiSwaggerInstrument(SwaggerInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "title": self.instrument_config.service_name,
            "description": self.instrument_config.service_description,
            "docs_url": self.instrument_config.swagger_path,
            "version": self.instrument_config.service_version,
        }

    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        if self.instrument_config.swagger_offline_docs:
            enable_offline_docs(application, static_files_handler=self.instrument_config.service_static_path)
        return application


@FastApiBootstrapper.use_instrument()
class FastApiCorsInstrument(CorsInstrument):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=self.instrument_config.cors_allowed_origins,
            allow_methods=self.instrument_config.cors_allowed_methods,
            allow_headers=self.instrument_config.cors_allowed_headers,
            allow_credentials=self.instrument_config.cors_allowed_credentials,
            allow_origin_regex=self.instrument_config.cors_allowed_origin_regex,
            expose_headers=self.instrument_config.cors_exposed_headers,
            max_age=self.instrument_config.cors_max_age,
        )
        return application
