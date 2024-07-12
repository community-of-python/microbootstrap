from __future__ import annotations
import dataclasses
import typing

from microbootstrap.helpers import merge_configs


if typing.TYPE_CHECKING:
    from pydantic import BaseModel


InstrumentConfigT = typing.TypeVar("InstrumentConfigT", bound="BaseModel")


@dataclasses.dataclass
class Instrument(typing.Protocol[InstrumentConfigT]):
    instrument_config: InstrumentConfigT

    def configure_instrument(
        self,
        incoming_config: InstrumentConfigT,
    ) -> None:
        self.instrument_config = merge_configs(self.instrument_config, incoming_config)

    def is_ready(self) -> bool:
        raise NotImplementedError

    def bootstrap(self) -> dict[str, typing.Any]:
        raise NotImplementedError

    def teardown(self) -> None:
        raise NotImplementedError
