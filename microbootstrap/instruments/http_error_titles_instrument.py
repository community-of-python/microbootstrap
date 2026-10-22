from __future__ import annotations
import http

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class HttpErrorTitlesConfig(BaseInstrumentConfig):
    http_error_titles_enabled: bool = False


class HttpErrorTitlesInstrument(Instrument[HttpErrorTitlesConfig]):
    instrument_name = "HTTP error titles"
    ready_condition = "Enable http_error_titles_enabled"

    def is_ready(self) -> bool:
        return self.instrument_config.http_error_titles_enabled

    @classmethod
    def get_config_type(cls) -> type[HttpErrorTitlesConfig]:
        return HttpErrorTitlesConfig

    @staticmethod
    def title_for_status(status_code: int) -> str:
        try:
            return http.HTTPStatus(status_code).phrase
        except ValueError:
            return "HTTP error"
