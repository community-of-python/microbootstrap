import dataclasses
import typing

from litestar.contrib.opentelemetry.config import OpenTelemetryConfig
from litestar.contrib.opentelemetry.middleware import OpenTelemetryInstrumentationMiddleware


if typing.TYPE_CHECKING:
    import litestar.types


@dataclasses.dataclass
class OpenTelemetryMiddlware:
    configuration: OpenTelemetryConfig

    def __call__(self, app: "litestar.types.ASGIApp") -> OpenTelemetryInstrumentationMiddleware:
        return OpenTelemetryInstrumentationMiddleware(app, self.configuration)
