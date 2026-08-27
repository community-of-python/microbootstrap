from __future__ import annotations
import typing

from faststream._internal.middlewares import BaseMiddleware
from opentelemetry import baggage, propagate

from microbootstrap.instruments.opentelemetry_instrument import opentelemetry_baggage_scope


if typing.TYPE_CHECKING:
    from faststream._internal.basic_types import AsyncFuncAny
    from faststream._internal.context import ContextRepo
    from faststream.message import StreamMessage


class FastStreamOpenTelemetryBaggageMiddleware:
    def __init__(self, *, baggage_span_attributes: typing.Mapping[str, str]) -> None:
        self.baggage_span_attributes = baggage_span_attributes

    def __call__(
        self,
        msg: typing.Any,  # noqa: ANN401
        /,
        *,
        context: ContextRepo,
    ) -> _FastStreamOpenTelemetryBaggageMiddleware:
        return _FastStreamOpenTelemetryBaggageMiddleware(
            msg,
            context=context,
            baggage_span_attributes=self.baggage_span_attributes,
        )


class _FastStreamOpenTelemetryBaggageMiddleware(BaseMiddleware[typing.Any, typing.Any]):
    def __init__(
        self,
        msg: typing.Any,  # noqa: ANN401
        /,
        *,
        context: ContextRepo,
        baggage_span_attributes: typing.Mapping[str, str],
    ) -> None:
        super().__init__(msg, context=context)
        self.baggage_span_attributes = baggage_span_attributes

    async def consume_scope(
        self,
        call_next: AsyncFuncAny,
        msg: StreamMessage[typing.Any],
    ) -> typing.Any:  # noqa: ANN401
        extracted_baggage: typing.Final = baggage.get_all(propagate.extract(msg.headers))
        with opentelemetry_baggage_scope(
            extracted_baggage,
            current_span_attributes=self.baggage_span_attributes,
        ):
            return await call_next(msg)

    async def publish_scope(
        self,
        call_next: typing.Callable[[typing.Any], typing.Awaitable[typing.Any]],
        cmd: typing.Any,  # noqa: ANN401
    ) -> typing.Any:  # noqa: ANN401
        for field in propagate.get_global_textmap().fields:
            cmd.headers.pop(field, None)
        propagate.inject(cmd.headers)
        return await call_next(cmd)
