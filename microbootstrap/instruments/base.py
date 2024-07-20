from __future__ import annotations
import abc
import dataclasses
import typing

import pydantic

from microbootstrap.helpers import merge_pydantic_configs


InstrumentConfigT = typing.TypeVar("InstrumentConfigT", bound="BaseInstrumentConfig")


class BaseInstrumentConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


@dataclasses.dataclass
class Instrument(abc.ABC, typing.Generic[InstrumentConfigT]):
    instrument_config: InstrumentConfigT

    def configure_instrument(
        self,
        incoming_config: InstrumentConfigT,
    ) -> None:
        self.instrument_config = merge_pydantic_configs(self.instrument_config, incoming_config)

    @property
    @abc.abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def bootsrap_final_result(self) -> dict[str, typing.Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def bootstrap(self) -> dict[str, typing.Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def teardown(self) -> None:
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def get_config_type(cls) -> type[InstrumentConfigT]:
        raise NotImplementedError
