import dataclasses
import typing

from faststream.asyncapi.schema import (
    Contact,
    ContactDict,
    ExternalDocs,
    ExternalDocsDict,
    License,
    LicenseDict,
    Tag,
    TagDict,
)
from faststream.broker.core.usecase import BrokerUsecase
from faststream.types import AnyDict, AnyHttpUrl, Lifespan, LoggerProto


@dataclasses.dataclass
class FastStreamConfig:
    broker: BrokerUsecase[typing.Any, typing.Any] | None = None
    logger: LoggerProto | None = None
    lifespan: Lifespan | None = None
    title: str | None = None
    version: str | None = None
    description: str | None = None
    terms_of_service: AnyHttpUrl | None = None
    license: License | LicenseDict | AnyDict | None = None
    contact: Contact | ContactDict | AnyDict | None = None
    tags: typing.Sequence[Tag | TagDict | AnyDict] | None = None
    external_docs: ExternalDocs | ExternalDocsDict | AnyDict | None = None
    identifier: str | None = None
    on_startup: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    after_startup: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    on_shutdown: typing.Sequence[typing.Callable[..., typing.Any]] = ()
    after_shutdown: typing.Sequence[typing.Callable[..., typing.Any]] = ()
