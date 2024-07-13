from __future__ import annotations
import dataclasses
import typing

from pydantic import BaseModel

from microbootstrap.helpers import merge_pydantic_configs


InstrumentConfigT = typing.TypeVar("InstrumentConfigT", bound="BaseInstrumentConfig")


class BaseInstrumentConfig(BaseModel):
    class Config:
        arbitrary_types_allowed = True


@dataclasses.dataclass
class Instrument(typing.Protocol[InstrumentConfigT]):
    instrument_config: InstrumentConfigT

    def configure_instrument(
        self,
        incoming_config: InstrumentConfigT,
    ) -> None:
        self.instrument_config = merge_pydantic_configs(self.instrument_config, incoming_config)

    @property
    def is_ready(self) -> bool:
        raise NotImplementedError

    @property
    def successful_bootstrap_result(self) -> dict[str, typing.Any]:
        raise NotImplementedError

    def bootstrap(self) -> dict[str, typing.Any]:
        raise NotImplementedError

    def teardown(self) -> None:
        raise NotImplementedError
