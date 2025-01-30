from __future__ import annotations
import dataclasses
import typing


if typing.TYPE_CHECKING:
    import faststream.asyncapi.schema as asyncapi
    from faststream.asgi.types import ASGIApp
    from faststream.broker.core.usecase import BrokerUsecase
    from faststream.types import AnyDict, AnyHttpUrl, Lifespan


@dataclasses.dataclass
class FastStreamConfig:
    broker: BrokerUsecase[typing.Any, typing.Any] | None = None
    asgi_routes: typing.Sequence[tuple[str, ASGIApp]] = ()
    lifespan: Lifespan | None = None
    terms_of_service: AnyHttpUrl | None = None
    license: asyncapi.License | asyncapi.LicenseDict | AnyDict | None = None
    contact: asyncapi.Contact | asyncapi.ContactDict | AnyDict | None = None
    tags: typing.Sequence[asyncapi.Tag | asyncapi.TagDict | AnyDict] | None = None
    external_docs: asyncapi.ExternalDocs | asyncapi.ExternalDocsDict | AnyDict | None = None
    identifier: str | None = None
    on_startup: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    after_startup: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    on_shutdown: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    after_shutdown: typing.Sequence[typing.Callable[..., typing.Any]] = ()
