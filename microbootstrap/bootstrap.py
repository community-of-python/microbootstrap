from __future__ import annotations
import contextlib
import typing


if typing.TYPE_CHECKING:
    import granian

    from microbootstrap.helpers import base as helpers_base
    from microbootstrap.settings.base import BootstrapSettings


def bootstrap(
    web_framework: type[
        helpers_base.BootstrapWebFrameworkBootstrapper[
            helpers_base.Application_contra,
            helpers_base.Settings_contra,
            helpers_base.ReturnType_co,
        ]
    ],
    settings: helpers_base.Settings_contra,
    app: helpers_base.Application_contra,
) -> helpers_base.ReturnType_co:
    web_framework_bootstrapper = web_framework()
    web_framework_bootstrapper.load_parameters(app=app, settings=settings)
    return web_framework_bootstrapper.initialize()


def teardown(
    web_framework: type[
        helpers_base.BootstrapWebFrameworkBootstrapper[
            helpers_base.Application_contra,
            helpers_base.Settings_contra,
            helpers_base.ReturnType_co,
        ]
    ],
    settings: helpers_base.Settings_contra,
    app: helpers_base.Application_contra,
) -> None:
    web_framework_bootstrapper = web_framework()
    web_framework_bootstrapper.load_parameters(app=app, settings=settings)
    web_framework_bootstrapper.teardown()


@contextlib.contextmanager
def enter_bootstrapper_context(
    *bootstrapper_classes: type[helpers_base.BootstrapServicesBootstrapper[helpers_base.Settings_contra]],
    settings: helpers_base.Settings_contra,
) -> typing.Iterator[None]:
    bootstrappers: typing.Final[list[helpers_base.BootstrapServicesBootstrapper[helpers_base.Settings_contra]]] = []
    for one_class in bootstrapper_classes:
        instance = one_class()
        instance.load_parameters(settings)
        instance.initialize()
        bootstrappers.append(instance)

    yield
    for one_bootstrapper in bootstrappers:
        one_bootstrapper.teardown()


def create_granian_server(
    target: str,
    settings: BootstrapSettings,
    **granian_options: typing.Any,  # noqa: ANN401
) -> granian.Granian:
    import granian
    from granian.constants import Interfaces, Loops
    from granian.log import log_levels_map

    return granian.Granian(
        target=target,
        address=settings.server_host,
        port=settings.server_port,
        interface=Interfaces.ASGI,
        loop=Loops.uvloop,
        workers=settings.server_workers_count,
        log_level={value: key for (key, value) in log_levels_map.items()}[settings.logging_log_level],
        reload=settings.server_reload,
        **granian_options,
    )
