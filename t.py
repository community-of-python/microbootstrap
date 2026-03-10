import typing

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper


def t():
    application: typing.Final = LitestarBootstrapper(LitestarSettings(opentelemetry_log_traces=True, service_debug=False)).bootstrap()
t()
t()
