from __future__ import annotations
import dataclasses
import typing


if typing.TYPE_CHECKING:
    from fast_depends import Provider
    from fast_depends.library.serializer import SerializerProto
    from faststream._internal.basic_types import (
        AnyCallable,
        Lifespan,
        LoggerProto,
    )
    from faststream._internal.broker import BrokerUsecase
    from faststream._internal.context import ContextRepo
    from faststream.asgi.types import ASGIApp
    from faststream.specification.base import SpecificationFactory


@dataclasses.dataclass
class FastStreamConfig:
    broker: BrokerUsecase[typing.Any, typing.Any] | None = None
    asgi_routes: typing.Sequence[tuple[str, ASGIApp]] = ()
    logger: LoggerProto | None = None
    provider: Provider | None = None
    serializer: SerializerProto | None = None
    context: ContextRepo | None = None
    lifespan: Lifespan | None = None
    on_startup: typing.Sequence[AnyCallable] = ()
    after_startup: typing.Sequence[AnyCallable] = ()
    on_shutdown: typing.Sequence[AnyCallable] = ()
    after_shutdown: typing.Sequence[AnyCallable] = ()
    specification: SpecificationFactory | None = None
