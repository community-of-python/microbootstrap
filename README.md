<p align="center">
    <img src="https://raw.githubusercontent.com/community-of-python/microbootstrap/main/logo.svg" width="350">
</p>
<br>
<p align="center">
    <a href="https://codecov.io/gh/community-of-python/microbootstrap" target="_blank">
        <img src="https://codecov.io/gh/community-of-python/microbootstrap/branch/main/graph/badge.svg">
    </a>
    <a href="https://pypi.org/project/microbootstrap/" target="_blank">
        <img src="https://img.shields.io/pypi/pyversions/microbootstrap">
    </a>
    <a href="https://pypi.org/project/microbootstrap/" target="_blank">
        <img src="https://img.shields.io/pypi/v/microbootstrap">
    </a>
</p>

# microbootstrap

<b>microbootstrap</b> helps you create applications with all necessary instruments already set up.

```python
# settings.py
from microbootstrap import LitestarSettings


class YourSettings(LitestarSettings):
    # Your settings stored here


settings = YourSettings()


# application.py
import litestar
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

from your_application.settings import settings

# Litestar application for use!
application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```

With <b>microbootstrap</b>, you get an application with built-in support for:

- `sentry`
- `prometheus`
- `opentelemetry`
- `logging`

<b>microbootstrap</b> supports only `litestar` framework for now.

Interested? Let's jump right into it ⚡

## Installation

You can install package with `pip` or `poetry`.

poetry:

```bash
$ poetry add microbootstrap -E litestar
```

pip:

```bash
$ poetry add microbootstrap[litestar]
```

## Quickstart

To manipulate your application, you can use settings object.

```python
from microbootstrap import LitestarSettings


class YourSettings(LitestarSettings):
    # General settings
    service_debug: bool = False
    service_name: str = "my-awesome-service"

    # Sentry settings
    sentry_dsn: str = "your-setnry-dsn"

    # Prometheus settings
    prometheus_metrics_path: str "/my-path"

    # Opentelemetry settings
    opentelemetry_container_name: str = "your-container"
    opentelemetry_endpoint: str = "/opentelemetry-endpoint"



settings = YourSettings()
```

Then, use the `Bootstrapper` object to create an application based on your settings.

```python
import litestar
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper

application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```

This way, you'll have an application with all the essential instruments already set up for you.

## Settings

The settings object is at the heart of microbootstrap.

All framework-related settings inherit from the `BaseBootstrapSettings` object. `BaseBootstrapSettings` defines parameters for the service and different instruments.

However, the number of parameters is <b>not limited</b> to those defined in `BaseBootstrapSettings`. You can add as many as you want.

These parameters can be pulled from your environment. By default, no prefix is added to these parameters.

Example:

```python
class YourSettings(BaseBootstrapSettings):
    service_debug: bool = True
    service_name: str = "micro-service"

    your_awesome_parameter: str = "really awesome"

    ... # Other settings here
```

To pull `your_awesome_parameter` from the environment, set the environment variable with the name `YOUR_AWESOME_PARAMETER`.

If you want to use a prefix when pulling parameters, set the `ENVIRONMENT_PREFIX` environment variable beforehand.

Example:

```bash
$ export ENVIRONMENT_PREFIX=YOUR_PREFIX_
```

Then the settings object will try to pull the variable with the name `YOUR_PREFIX_YOUR_AWESOME_PARAMETER`.

## Service settings

Every settings object for every framework contains service parameters that can be used by different instruments.

You can set them manually, or set the appropriate environment variables and let <b>microbootstrap</b> pull them automatically.

```python
from microbootstrap.bootstrappers.litestar import BaseBootstrapSettings


class ServiceSettings(BaseBootstrapSettings):
    service_debug: bool = True
    service_environment: str | None = None
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"

    ... # Other settings here

```

## Instruments

Currently, these instruments are already supported for bootstrapping:

- `sentry`
- `prometheus`
- `opentelemetry`
- `logging`

Let's make it clear, what it takes to bootstrap them.

### Sentry

To bootstrap Sentry, you need to provide at least the `sentry_dsn`.  
You can also provide other parameters through the settings object.

```python
from microbootstrap.bootstrappers.litestar import BaseBootstrapSettings


class YourSettings(BaseBootstrapSettings):
    service_environment: str | None = None

    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] = []
    sentry_additional_params: dict[str, typing.Any] = {}

    ... # Other settings here
```

All these settings are then passed to [sentry-sdk](https://pypi.org/project/sentry-sdk/) package, completing your Sentry integration.

### Prometheus

To bootstrap Prometheus, you need to provide at least the `prometheus_metrics_path`.  
You can also provide other parameters through the settings object.

```python
from microbootstrap.bootstrappers.litestar import BaseBootstrapSettings


class YourSettings(BaseBootstrapSettings):
    service_name: str

    prometheus_metrics_path: str = "/metrics"
    prometheus_additional_params: dict[str, typing.Any] = {}

    ... # Other settings here
```

These settings will be passed to [prometheus-client](https://pypi.org/project/prometheus-client/).
Still underlying top-level Prometheus library can change from framework to framework, but overall, you'll get a metrics handler at the provided path.

By default, metrics are available at the `/metrics` path.

### Opentelemetry

Opentelemetry requires a lot of parameters to be bootstrapped:

- `service_name`
- `service_version`
- `opentelemetry_endpoint`
- `opentelemetry_namespace`
- `opentelemetry_container_name`.

But you can also provide some more if you need.

```python
from microbootstrap.bootstrappers.litestar import BaseBootstrapSettings
from microbootstrap.instruments.opentelemetry_instrument import OpenTelemetryInstrumentor


class YourSettings(BaseBootstrapSettings):
    service_name: str
    service_version: str

    opentelemetry_container_name: str | None = None
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_insecure: bool = True
    opentelemetry_insrtumentors: list[OpenTelemetryInstrumentor] = []
    opentelemetry_exclude_urls: list[str] = []

    ... # Other settings here
```

All these settings are then passed to [opentelemetry](https://opentelemetry.io/), completing your Opentelemetry integration.

## Logging

<b>microbootstrap</b> provides in-memory json logging using [structlog](https://pypi.org/project/structlog/).  
To learn more about in-memory logging, check out [MemoryHandler](https://docs.python.org/3/library/logging.handlers.html#memoryhandler)

To use this feature, your application has to be in non-debug mode, i.e. `service_debug` has to be `False`

```python
import logging

from microbootstrap.bootstrappers.litestar import BaseBootstrapSettings


class YourSettings(BaseBootstrapSettings):
    service_debug: bool = True

    logging_log_level: int = logging.INFO
    logging_flush_level: int = logging.ERROR
    logging_buffer_capacity: int = 10
    logging_unset_handlers: list[str] = ["uvicorn", "uvicorn.access"]
    logging_extra_processors: list[typing.Any] = []
    logging_exclude_endpoints: list[str] = []
```

Parameters description:

- `logging_log_level` - default log level.
- `logging_flush_level` - all messages will be flushed from buffer, when log with this level appears.
- `logging_buffer_capacity` - how much messages your buffer will store, until flushed.
- `logging_unset_handlers` - unset logger handlers.
- `logging_extra_processors` - set additional structlog processors if you have some.
- `logging_exclude_endpoints` - remove logging on certain endpoints.

## Configuration

Despite settings being pretty convenient mechanism, it's not always possible to store everything in settings.

Sometimes one needs to configure some instrument on the spot, here, how it's being done.

### Instruments configuration

To configure instruemt manually, you have to import one of available configs from <b>microbootstrap</b>:

- `SentryConfig`
- `OpentelemetryConfig`
- `PrometheusConfig`
- `LoggingConfig`

And pass them into `.configure_instrument` or `.configure_instruments` bootstrapper method.

```python
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig


application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configure_instrument(SentryConfig(sentry_dsn="https://new-dsn"))
    .configure_instrument(OpentelemetryConfig(sentry_dsn="/new-endpoint"))
    .bootstrap()
)
```

Or

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

Application can be configured similarly

```python
import litestar
from litestar.config.app import AppConfig

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap import SentryConfig, OpentelemetryConfig


@litestar.get("/my-handler")
async def my_handler() -> str:
    return "Ok"

application: litestar.Litestar = (
    LitestarBootstrapper(settings)
    .configur_application(AppConfig(route_handlers=[my_handler]))
    .bootstrap()
)
```

> ### Important
>
> When configuring parameters with simple data types such as: `str`, `int`, `float`, e.t.c.  
> Those variables are rewriting previous values.
>
> Example
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
> In this example application will be bootstrapped with new `https://my-new-configured-sentry-dsn` sentry dsn
> instead of old one.
>
> But if you configure parameters with complex data types such as: `list`, `tuple`, `dict` or `set`.  
> They are being expanded or merged into each other.
>
> Example
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
> In this case prometheus will receive `{"first_value: 1", "second_value": 2}` inside `prometheus_additional_params`  
> This is also true for `list`, `tuple` and `set`s

## Advanced

If you miss some instrument, you can add your own.  
Essentialy, `Instrument` is just a class with some abstractmethods.  
Every instrument uses some config, so that's first thing, you have to define.

```python
from microbootstrap.instruments.base import BaseInstrumentConfig


class MyInstrumentConfig(BaseInstrumentConfig):
    your_string_parameter: str
    your_list_parameter: list
```

After that, you can create an instrument class, that is inheriting from `Instrument` and accepts your config as generic parameter

```python
from microbootstrap.instruments.base import Instrument


class MyInstrument(Instrument[MyInstrumentConfig]):
    def write_status(self, console_writer: ConsoleWriter) -> None:
        pass

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

And now you can define behaviour of your instrument

- `write_status` - writes status to console, indicating, is instrument bootstrapped.
- `is_ready` - defines ready for bootstrapping state of instrument, based on it's config values.
- `teardown` - graceful shutdown for instrument during application shutdown.
- `bootstrap` - main instrument's logic.

When you have a carcass of instrument, you can adapt it for every framework existing.  
Let's adapt it for litestar for example

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

To bind instrument to a bootstrapper, you have to use `.use_instrument` decorator.

To add some extra parameters to application you can use:

- `bootstrap_before` - add some arguments to application config before creation
- `bootstrap_after` - add some arguments to application after creation

After that you can use your instrument during bootstrap process

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

or you can fill those parameters inside your main settings object

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
