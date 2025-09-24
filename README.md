<p align="center">
    <img src="https://raw.githubusercontent.com/community-of-python/microbootstrap/main/logo.svg" width="350">
</p>
<br>
<p align="center">
    <a href="https://codecov.io/gh/community-of-python/microbootstrap" target="_blank"><img src="https://codecov.io/gh/community-of-python/microbootstrap/branch/main/graph/badge.svg"></a>
    <a href="https://pypi.org/project/microbootstrap/" target="_blank"><img src="https://img.shields.io/pypi/pyversions/microbootstrap"></a>
    <a href="https://pypi.org/project/microbootstrap/" target="_blank"><img src="https://img.shields.io/pypi/v/microbootstrap"></a>
    <a href="https://pypistats.org/packages/microbootstrap" target="_blank"><img src="https://img.shields.io/pypi/dm/microbootstrap"></a>
</p>

<b>microbootstrap</b> assists you in creating applications with all the necessary instruments already set up.

```python
# settings.py
from microbootstrap import LitestarSettings


class YourSettings(LitestarSettings):
    ...  # Your settings are stored here


settings = YourSettings()


# application.py
import litestar
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

from your_application.settings import settings

# Use the Litestar application!
application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```

With <b>microbootstrap</b>, you receive an application with lightweight built-in support for:

- `sentry`
- `prometheus`
- `opentelemetry`
- `logging`
- `cors`
- `swagger` - with additional offline version support
- `health-checks`

Those instruments can be bootstrapped for:

- `fastapi`,
- `litestar`,
- or `faststream` service,
- or even a service that doesn't use one of these frameworks.

Interested? Let's dive right in ⚡

## Table of Contents

- [Installation](#installation)
- [Quickstart](#quickstart)
- [Settings](#settings)
- [Service settings](#service-settings)
- [Instruments](#instruments)
  - [Sentry](#sentry)
  - [Prometheus](#prometheus)
  - [Opentelemetry](#opentelemetry)
  - [Logging](#logging)
  - [CORS](#cors)
  - [Swagger](#swagger)
  - [Health checks](#health-checks)
- [Configuration](#configuration)
  - [Instruments configuration](#instruments-configuration)
  - [Application configuration](#application-configuration)
- [Advanced](#advanced)

## Installation

Also, you can specify extras during installation for concrete framework:

- `fastapi`
- `litestar`
- `faststream` (ASGI app)

Also we have `granian` extra that is requires for `create_granian_server`.

For uv:

```bash
uv add "microbootstrap[fastapi]"
```

For poetry:

```bash
poetry add microbootstrap -E fastapi
```

For pip:

```bash
pip install "microbootstrap[fastapi]"
```

## Quickstart

To configure your application, you can use the settings object.

```python
from microbootstrap import LitestarSettings


class YourSettings(LitestarSettings):
    # General settings
    service_debug: bool = False
    service_name: str = "my-awesome-service"

    # Sentry settings
    sentry_dsn: str = "your-sentry-dsn"

    # Prometheus settings
    prometheus_metrics_path: str = "/my-path"

    # Opentelemetry settings
    opentelemetry_container_name: str = "your-container"
    opentelemetry_endpoint: str = "/opentelemetry-endpoint"



settings = YourSettings()
```

Next, use the `Bootstrapper` object to create an application based on your settings.

```python
import litestar
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```

This approach will provide you with an application that has all the essential instruments already set up for you.

### FastAPI

```python
import fastapi

from microbootstrap import FastApiSettings
from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper


class YourSettings(FastApiSettings):
    # General settings
    service_debug: bool = False
    service_name: str = "my-awesome-service"

    # Sentry settings
    sentry_dsn: str = "your-sentry-dsn"

    # Prometheus settings
    prometheus_metrics_path: str = "/my-path"

    # Opentelemetry settings
    opentelemetry_container_name: str = "your-container"
    opentelemetry_endpoint: str = "/opentelemetry-endpoint"


settings = YourSettings()

application: fastapi.FastAPI = FastApiBootstrapper(settings).bootstrap()
```

### FastStream

```python
from faststream.asgi import AsgiFastStream

from microbootstrap import FastStreamSettings
from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper


class YourSettings(FastStreamSettings):
    # General settings
    service_debug: bool = False
    service_name: str = "my-awesome-service"

    # Sentry settings
    sentry_dsn: str = "your-sentry-dsn"

    # Prometheus settings
    prometheus_metrics_path: str = "/my-path"

    # Opentelemetry settings
    opentelemetry_container_name: str = "your-container"
    opentelemetry_endpoint: str = "/opentelemetry-endpoint"


settings = YourSettings()

application: AsgiFastStream = FastStreamBootstrapper(settings).bootstrap()
```

## Settings

The settings object is the core of microbootstrap.

All framework-related settings inherit from the `BaseServiceSettings` object. `BaseServiceSettings` defines parameters for the service and various instruments.

However, the number of parameters is <b>not confined</b> to those defined in `BaseServiceSettings`. You can add as many as you need.

These parameters can be sourced from your environment. By default, no prefix is added to these parameters.

Example:

```python
class YourSettings(BaseServiceSettings):
    service_debug: bool = True
    service_name: str = "micro-service"

    your_awesome_parameter: str = "really awesome"

    ... # Other settings here
```

To source `your_awesome_parameter` from the environment, set the environment variable named `YOUR_AWESOME_PARAMETER`.

If you prefer to use a prefix when sourcing parameters, set the `ENVIRONMENT_PREFIX` environment variable in advance.

Example:

```bash
$ export ENVIRONMENT_PREFIX=YOUR_PREFIX_
```

Then the settings object will attempt to source the variable named `YOUR_PREFIX_YOUR_AWESOME_PARAMETER`.

## Service settings

Each settings object for every framework includes service parameters that can be utilized by various instruments.

You can configure them manually, or set the corresponding environment variables and let <b>microbootstrap</b> to source them automatically.

```python
from microbootstrap.settings import BaseServiceSettings


class ServiceSettings(BaseServiceSettings):
    service_debug: bool = True
    service_environment: str | None = None
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"

    ... # Other settings here

```

## Instruments

At present, the following instruments are supported for bootstrapping:

- `sentry`
- `prometheus`
- `opentelemetry`
- `pyroscope`
- `logging`
- `cors`
- `swagger`

Let's clarify the process required to bootstrap these instruments.

### [Sentry](https://sentry.io/)

To bootstrap Sentry, you must provide at least the `sentry_dsn`.
Additional parameters can also be supplied through the settings object.

```python
from microbootstrap.settings import BaseServiceSettings


class YourSettings(BaseServiceSettings):
    service_environment: str | None = None

    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_max_value_length: int = 16384
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] = []
    sentry_additional_params: dict[str, typing.Any] = {}
    sentry_tags: dict[str, str] | None = None
    sentry_opentelemetry_trace_url_template: str | None = None

    ... # Other settings here
```

These settings are subsequently passed to the [sentry-sdk](https://pypi.org/project/sentry-sdk/) package, finalizing your Sentry integration.

Parameter descriptions:

- `service_environment` - The environment name for Sentry events.
- `sentry_dsn` - The Data Source Name for your Sentry project.
- `sentry_traces_sample_rate` - The rate at which traces are sampled (via Sentry Tracing, not OpenTelemetry).
- `sentry_sample_rate` - The rate at which transactions are sampled.
- `sentry_max_breadcrumbs` - The maximum number of breadcrumbs to keep.
- `sentry_max_value_length` - The maximum length of values in Sentry events.
- `sentry_attach_stacktrace` - Whether to attach stacktraces to messages.
- `sentry_integrations` - A list of Sentry integrations to enable.
- `sentry_additional_params` - Additional parameters to pass to Sentry SDK.
- `sentry_tags` - Tags to apply to all Sentry events.
- `sentry_opentelemetry_trace_url_template` - Template for OpenTelemetry trace URLs to add to Sentry events (example: `"https://example.com/traces/{trace_id}"`).

### [Prometheus](https://prometheus.io/)

Prometheus integration presents a challenge because the underlying libraries for `FastAPI`, `Litestar` and `FastStream` differ significantly, making it impossible to unify them under a single interface. As a result, the Prometheus settings for `FastAPI`, `Litestar` and `FastStream` must be configured separately.

#### FastAPI

To bootstrap prometheus you have to provide `prometheus_metrics_path`

```python
from microbootstrap.settings import FastApiSettings


class YourSettings(FastApiSettings):
    service_name: str

    prometheus_metrics_path: str = "/metrics"
    prometheus_metrics_include_in_schema: bool = False
    prometheus_instrumentator_params: dict[str, typing.Any] = {}
    prometheus_instrument_params: dict[str, typing.Any] = {}
    prometheus_expose_params: dict[str, typing.Any] = {}

    ... # Other settings here
```

Parameters description:

- `service_name` - will be attached to metrics's names, but has to be named in [snake_case](https://en.wikipedia.org/wiki/Snake_case).
- `prometheus_metrics_path` - path to metrics handler.
- `prometheus_metrics_include_in_schema` - whether to include metrics route in OpenAPI schema.
- `prometheus_instrumentator_params` - will be passed to `Instrumentor` during initialization.
- `prometheus_instrument_params` - will be passed to `Instrumentor.instrument(...)`.
- `prometheus_expose_params` - will be passed to `Instrumentor.expose(...)`.

FastAPI prometheus bootstrapper uses [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) that's why there are three different dict for parameters.

#### Litestar

To bootstrap prometheus you have to provide `prometheus_metrics_path`

```python
from microbootstrap.settings import LitestarSettings


class YourSettings(LitestarSettings):
    service_name: str

    prometheus_metrics_path: str = "/metrics"
    prometheus_additional_params: dict[str, typing.Any] = {}

    ... # Other settings here
```

Parameters description:

- `service_name` - will be attached to metric's names, there are no name restrictions.
- `prometheus_metrics_path` - path to metrics handler.
- `prometheus_additional_params` - will be passed to `litestar.contrib.prometheus.PrometheusConfig`.

#### FastStream

To bootstrap prometheus you have to provide `prometheus_metrics_path` and `prometheus_middleware_cls`:

```python
from microbootstrap import FastStreamSettings
from faststream.redis.prometheus import RedisPrometheusMiddleware


class YourSettings(FastStreamSettings):
    service_name: str

    prometheus_metrics_path: str = "/metrics"
    prometheus_middleware_cls: type[FastStreamPrometheusMiddlewareProtocol] | None = RedisPrometheusMiddleware

    ... # Other settings here
```

Parameters description:

- `service_name` - will be attached to metric's names, there are no name restrictions.
- `prometheus_metrics_path` - path to metrics handler.
- `prometheus_middleware_cls` - Prometheus middleware for your broker.

### [OpenTelemetry](https://opentelemetry.io/)

To bootstrap OpenTelemetry, you must provide `opentelemetry_endpoint` or set `opentelemetry_log_traces` to `True`.

However, additional parameters can also be supplied if needed.

```python
from microbootstrap.settings import BaseServiceSettings, FastStreamPrometheusMiddlewareProtocol
from microbootstrap.instruments.opentelemetry_instrument import OpenTelemetryInstrumentor


class YourSettings(BaseServiceSettings):
    service_name: str
    service_version: str

    opentelemetry_service_name: str | None = None
    opentelemetry_container_name: str | None = None
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_insecure: bool = True
    opentelemetry_instrumentors: list[OpenTelemetryInstrumentor] = []
    opentelemetry_exclude_urls: list[str] = []

    ... # Other settings here
```

Parameters description:

- `service_name` - will be passed to the `Resource`.
- `service_version` - will be passed to the `Resource`.
- `opentelemetry_service_name` - if provided, will be passed to the `Resource` instead of `service_name`.
- `opentelemetry_endpoint` - will be passed to `OTLPSpanExporter` as endpoint.
- `opentelemetry_namespace` - will be passed to the `Resource`.
- `opentelemetry_insecure` - is opentelemetry connection secure.
- `opentelemetry_container_name` - will be passed to the `Resource`.
- `opentelemetry_instrumentors` - a list of extra instrumentors.
- `opentelemetry_exclude_urls` - list of ignored urls.
- `opentelemetry_log_traces` - traces will be logged to stdout.

These settings are subsequently passed to [opentelemetry](https://opentelemetry.io/), finalizing your Opentelemetry integration.

#### FastStream

For FastStream you also should pass `opentelemetry_middleware_cls` - OpenTelemetry middleware for your broker

```python
from microbootstrap import FastStreamSettings, FastStreamTelemetryMiddlewareProtocol
from faststream.redis.opentelemetry import RedisTelemetryMiddleware


class YourSettings(FastStreamSettings):
    ...
    opentelemetry_middleware_cls: type[FastStreamTelemetryMiddlewareProtocol] | None = RedisTelemetryMiddleware
    ...
```

### [Pyroscope](https://pyroscope.io)

To integrate Pyroscope, specify the `pyroscope_endpoint`.

- The `opentelemetry_service_name` will be used as the application name.
- `service_namespace` tag will be added with `opentelemetry_namespace` value.
- You can also set `pyroscope_sample_rate`, `pyroscope_auth_token`, `pyroscope_tags` and `pyroscope_additional_params` — params that will be passed to `pyroscope.configure`.

When both Pyroscope and OpenTelemetry are enabled, profile span IDs will be included in traces using [`pyroscope-otel`](https://github.com/grafana/otel-profiling-python) for correlation.

Note that Pyroscope integration is not supported on Windows.

### Logging

<b>microbootstrap</b> provides in-memory JSON logging through the use of [structlog](https://pypi.org/project/structlog/).
For more information on in-memory logging, refer to [MemoryHandler](https://docs.python.org/3/library/logging.handlers.html#memoryhandler).

To utilize this feature, your application must be in non-debug mode, meaning `service_debug` should be set to `False`.

```python
import logging

from microbootstrap.settings import BaseServiceSettings


class YourSettings(BaseServiceSettings):
    service_debug: bool = False

    logging_log_level: int = logging.INFO
    logging_flush_level: int = logging.ERROR
    logging_buffer_capacity: int = 10
    logging_unset_handlers: list[str] = ["uvicorn", "uvicorn.access"]
    logging_extra_processors: list[typing.Any] = []
    logging_exclude_endpoints: list[str] = ["/health/", "/metrics"]
    logging_turn_off_middleware: bool = False
```

Parameters description:

- `logging_log_level` - The default log level.
- `logging_flush_level` - All messages will be flushed from the buffer when a log with this level appears.
- `logging_buffer_capacity` - The number of messages your buffer will store before being flushed.
- `logging_unset_handlers` - Unset logger handlers.
- `logging_extra_processors` - Set additional structlog processors if needed.
- `logging_exclude_endpoints` - Exclude logging on specific endpoints.
- `logging_turn_off_middleware` - Turning off logging middleware.

### CORS

```python
from microbootstrap.settings import BaseServiceSettings


class YourSettings(BaseServiceSettings):
    cors_allowed_origins: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_methods: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_headers: list[str] = pydantic.Field(default_factory=list)
    cors_exposed_headers: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_credentials: bool = False
    cors_allowed_origin_regex: str | None = None
    cors_max_age: int = 600
```

Parameter descriptions:

- `cors_allowed_origins` - A list of origins that are permitted.
- `cors_allowed_methods` - A list of HTTP methods that are allowed.
- `cors_allowed_headers` - A list of headers that are permitted.
- `cors_exposed_headers` - A list of headers that are exposed via the 'Access-Control-Expose-Headers' header.
- `cors_allowed_credentials` - A boolean value that dictates whether or not to set the 'Access-Control-Allow-Credentials' header.
- `cors_allowed_origin_regex` - A regex used to match against origins.
- `cors_max_age` - The response caching Time-To-Live (TTL) in seconds, defaults to 600.

### Swagger

```python
from microbootstrap.settings import BaseServiceSettings


class YourSettings(BaseServiceSettings):
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"
    service_static_path: str = "/static"

    swagger_path: str = "/docs"
    swagger_offline_docs: bool = False
    swagger_extra_params: dict[str, Any] = {}
```

Parameter descriptions:

- `service_name` - The name of the service, which will be displayed in the documentation.
- `service_description` - A brief description of the service, which will also be displayed in the documentation.
- `service_version` - The current version of the service.
- `service_static_path` - The path for static files in the service.
- `swagger_path` - The path where the documentation can be found.
- `swagger_offline_docs` - A boolean value that, when set to True, allows the Swagger JS bundles to be accessed offline. This is because the service starts to host via static.
- `swagger_extra_params` - Additional parameters to pass into the OpenAPI configuration.

#### FastStream AsyncAPI documentation

AsyncAPI documentation is available by default under `/asyncapi` route. You can change that by setting `asyncapi_path`:

```python
from microbootstrap import FastStreamSettings


class YourSettings(FastStreamSettings):
    asyncapi_path: str | None = None
```

### Health checks

```python
from microbootstrap.settings import BaseServiceSettings


class YourSettings(BaseServiceSettings):
    service_name: str = "micro-service"
    service_version: str = "1.0.0"

    health_checks_enabled: bool = True
    health_checks_path: str = "/health/"
    health_checks_include_in_schema: bool = False
```

Parameter descriptions:

- `service_name` - Will be displayed in health check response.
- `service_version` - Will be displayed in health check response.
- `health_checks_enabled` - Must be True to enable health checks.
- `health_checks_path` - Path for health check handler.
- `health_checks_include_in_schema` - Must be True to include `health_checks_path` (`/health/`) in OpenAPI schema.

## Configuration

While settings provide a convenient mechanism, it's not always feasible to store everything within them.

There may be cases where you need to configure a tool directly. Here's how it can be done.

### Instruments configuration

To manually configure an instrument, you need to import one of the available configurations from <b>microbootstrap</b>:

- `SentryConfig`
- `OpentelemetryConfig`
- `PrometheusConfig`
- `LoggingConfig`
- `SwaggerConfig`
- `CorsConfig`

These configurations can then be passed into the `.configure_instrument` or `.configure_instruments` bootstrapper methods.

```python
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig


application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configure_instrument(SentryConfig(sentry_dsn="https://new-dsn"))
    .configure_instrument(OpentelemetryConfig(opentelemetry_endpoint="/new-endpoint"))
    .bootstrap()
)
```

Alternatively,

```python
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig


application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configure_instruments(
        SentryConfig(sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0"),
        OpentelemetryConfig(opentelemetry_endpoint="/new-endpoint")
    )
    .bootstrap()
)
```

### Application configuration

The application can be configured in a similar manner:

```python
import litestar

from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig


@litestar.get("/my-handler")
async def my_handler() -> str:
    return "Ok"

application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configure_application(LitestarConfig(route_handlers=[my_handler]))
    .bootstrap()
)
```

> ### Important
>
> When configuring parameters with simple data types such as: `str`, `int`, `float`, etc., these variables overwrite previous values.
>
> Example:
>
> ```python
> from microbootstrap import LitestarSettings, SentryConfig
>
>
> class YourSettings(LitestarSettings):
>     sentry_dsn: str = "https://my-sentry-dsn"
>
>
> application: litestar.Litestar = (
>     LitestarBootstrapper(YourSettings())
>     .configure_instrument(
>         SentryConfig(sentry_dsn="https://my-new-configured-sentry-dsn")
>     )
>     .bootstrap()
> )
> ```
>
> In this example, the application will be bootstrapped with the new `https://my-new-configured-sentry-dsn` Sentry DSN, replacing the old one.
>
> However, when you configure parameters with complex data types such as: `list`, `tuple`, `dict`, or `set`, they are expanded or merged.
>
> Example:
>
> ```python
> from microbootstrap import LitestarSettings, PrometheusConfig
>
>
> class YourSettings(LitestarSettings):
>     prometheus_additional_params: dict[str, Any] = {"first_value": 1}
>
>
> application: litestar.Litestar = (
>     LitestarBootstrapper(YourSettings())
>     .configure_instrument(
>         PrometheusConfig(prometheus_additional_params={"second_value": 2})
>     )
>     .bootstrap()
> )
> ```
>
> In this case, Prometheus will receive `{"first_value": 1, "second_value": 2}` inside `prometheus_additional_params`. This is also true for `list`, `tuple`, and `set`.

### Using microbootstrap without a framework

When working on projects that don't use Litestar or FastAPI, you can still take advantage of monitoring and logging capabilities using `InstrumentsSetupper`. This class sets up Sentry, OpenTelemetry, Pyroscope and Logging instruments in a way that's easy to integrate with your project.

You can use `InstrumentsSetupper` as a context manager, like this:

```python
from microbootstrap.instruments_setupper import InstrumentsSetupper
from microbootstrap import InstrumentsSetupperSettings


class YourSettings(InstrumentsSetupperSettings):
    ...


with InstrumentsSetupper(YourSettings()):
    while True:
        print("doing something useful")
        time.sleep(1)
```

Alternatively, you can use the `setup()` and `teardown()` methods instead of a context manager:

```python
current_setupper = InstrumentsSetupper(YourSettings())
current_setupper.setup()
try:
    while True:
        print("doing something useful")
        time.sleep(1)
finally:
    current_setupper.teardown()
```

Like bootstrappers, you can reconfigure instruments using the `configure_instrument()` and `configure_instruments()` methods.

## Advanced

If you miss some instrument, you can add your own.
Essentially, `Instrument` is just a class with some abstractmethods.
Every instrument uses some config, so that's first thing, you have to define.

```python
from microbootstrap.instruments.base import BaseInstrumentConfig


class MyInstrumentConfig(BaseInstrumentConfig):
    your_string_parameter: str
    your_list_parameter: list
```

Next, you can create an instrument class that inherits from `Instrument` and accepts your configuration as a generic parameter.

```python
from microbootstrap.instruments.base import Instrument


class MyInstrument(Instrument[MyInstrumentConfig]):
    instrument_name: str
    ready_condition: str

    def is_ready(self) -> bool:
        pass

    def teardown(self) -> None:
        pass

    def bootstrap(self) -> None:
        pass

    @classmethod
    def get_config_type(cls) -> type[MyInstrumentConfig]:
        return MyInstrumentConfig
```

Now, you can define the behavior of your instrument.

Attributes:

- `instrument_name` - This will be displayed in your console during bootstrap.
- `ready_condition` - This will be displayed in your console during bootstrap if the instrument is not ready.

Methods:

- `is_ready` - This defines the readiness of the instrument for bootstrapping, based on its configuration values. This is required.
- `teardown` - This allows for a graceful shutdown of the instrument during application shutdown. This is not required.
- `bootstrap` - This is the main logic of the instrument. This is not required.

Once you have the framework of the instrument, you can adapt it for any existing framework. For instance, let's adapt it for litestar.

```python
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

@LitestarBootstrapper.use_instrument()
class LitestarMyInstrument(MyInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        pass

    def bootstrap_after(self, application: litestar.Litestar) -> dict[str, typing.Any]:
        pass
```

To bind the instrument to a bootstrapper, use the `.use_instrument` decorator.

To add extra parameters to the application, you can use:

- `bootstrap_before` - This adds arguments to the application configuration before creation.
- `bootstrap_after` - This adds arguments to the application after creation.

Afterwards, you can use your instrument during the bootstrap process.

```python
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig

from your_app import MyInstrumentConfig


application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configure_instrument(
        MyInstrumentConfig(
            your_string_parameter="very-nice-parameter",
            your_list_parameter=["very-special-list"],
        )
    )
    .bootstrap()
)
```

Alternatively, you can fill these parameters within your main settings object.

```python
from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

from your_app import MyInstrumentConfig


class YourSettings(LitestarSettings, MyInstrumentConfig):
    your_string_parameter: str = "very-nice-parameter"
    your_list_parameter: list = ["very-special-list"]

settings = YourSettings()

application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```
