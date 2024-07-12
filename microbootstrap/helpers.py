import dataclasses
import typing

from microbootstrap import exceptions


if typing.TYPE_CHECKING:
    from pydantic import BaseModel


PydanticConfigT = typing.TypeVar("PydanticConfigT", bound="BaseModel")


def merge_pydantic_configs(
    config_to_merge: PydanticConfigT,
    config_with_changes: PydanticConfigT,
) -> PydanticConfigT:
    config_class: typing.Final = config_to_merge.__class__
    resulting_dict_config: typing.Final = merge_dict_configs(
        config_to_merge.model_dump(),
        config_with_changes.model_dump_json(exclude_defaults=True, exclude_unset=True),
    )
    return config_class(**resulting_dict_config)


def merge_dataclasses_configs(
    config_to_merge: dataclasses._DataclassT,
    config_with_changes: dataclasses._DataclassT,
) -> dataclasses._DataclassT:
    config_class: typing.Final = config_to_merge.__class__
    resulting_dict_config: typing.Final = merge_dict_configs(
        dataclasses.asdict(config_to_merge),
        dataclasses.asdict(config_with_changes),
    )
    return config_class(**resulting_dict_config)


def merge_dict_configs(
    config_dict: dict[str, typing.Any],
    changes_dict: dict[str, typing.Any],
) -> dict[str, typing.Any]:
    for change_key, change_value in changes_dict.items():
        config_value = config_dict.get(change_key)
        if isinstance(config_value, list):
            if not isinstance(change_value, list):
                raise exceptions.MicroBootstrapBaseError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = [*config_value, *change_value]

        elif isinstance(config_value, dict):
            if not isinstance(change_value, dict):
                raise exceptions.MicroBootstrapBaseError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = {**config_value, **change_value}

        else:
            config_dict[change_key] = change_value

    return config_dict
