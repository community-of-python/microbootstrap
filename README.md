<img src="./logo.svg" width="350"/>

[![codecov](https://codecov.io/gh/community-of-python/microbootstrap/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/yourrepo)

# microbootstrap

This package helps you create application with all necessary instruments already set up

- `sentry`
- `prometheus`
- `opentelemetry`
- `logging`

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

# Litestar application with all instruments ready for use!
application: litestar.Litestar = LitestarBootstrapper(settings).bootstrap()
```

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
