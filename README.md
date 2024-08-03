<p align="center">
<img src="./logo.svg" width="350"/>
</p>

[![codecov](https://codecov.io/gh/community-of-python/microbootstrap/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/yourrepo)

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

Interested? Let's jump right into it ⚡

## Installation

You can install `microbootstrap` with extra for framework you need.

poetry:

```bash
$ poetry add microbootstrap -E litestar
# or
$ poetry add microbootstrap -E fastapi
```

pip:

```bash
$ pip install microbootsrap[litestar]
# or
$ pip install microbootsrap[fastapi]
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

The underlying Prometheus library can change from framework to framework, but overall, you'll get a metrics handler at the provided path.  
By default, metrics are available at the `/metrics` path.

### Opentelemetry

Opentelemetry requires a lot of params to work correctly:

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
