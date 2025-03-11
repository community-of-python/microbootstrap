import dataclasses
import re
import typing
from dataclasses import _MISSING_TYPE

from microbootstrap import exceptions


if typing.TYPE_CHECKING:
    from dataclasses import _DataclassT

    from pydantic import BaseModel


PydanticConfigT = typing.TypeVar("PydanticConfigT", bound="BaseModel")
VALID_PATH_PATTERN: typing.Final = r"^(/[a-zA-Z0-9_-]+)+/?$"


def dataclass_to_dict_no_defaults(dataclass_to_convert: "_DataclassT") -> dict[str, typing.Any]:
    conversion_result: typing.Final = {}
    for dataclass_field in dataclasses.fields(dataclass_to_convert):
        value = getattr(dataclass_to_convert, dataclass_field.name)
        if isinstance(dataclass_field.default, _MISSING_TYPE):
            conversion_result[dataclass_field.name] = value
            continue
        if dataclass_field.default != value and isinstance(dataclass_field.default_factory, _MISSING_TYPE):
            conversion_result[dataclass_field.name] = value
            continue
        if value != dataclass_field.default and value != dataclass_field.default_factory():  # type: ignore[misc]
            conversion_result[dataclass_field.name] = value

    return conversion_result


def merge_pydantic_configs(
    config_to_merge: PydanticConfigT,
    config_with_changes: PydanticConfigT,
) -> PydanticConfigT:
    initial_fields: typing.Final = dict(config_to_merge)
    changed_fields: typing.Final = {
        one_field_name: getattr(config_with_changes, one_field_name)
        for one_field_name in config_with_changes.model_fields_set
    }
    merged_fields: typing.Final = merge_dict_configs(initial_fields, changed_fields)
    return config_to_merge.model_copy(update=merged_fields)


def merge_dataclasses_configs(
    config_to_merge: "_DataclassT",
    config_with_changes: "_DataclassT",
) -> "_DataclassT":
    config_class: typing.Final = config_to_merge.__class__
    resulting_dict_config: typing.Final = merge_dict_configs(
        dataclass_to_dict_no_defaults(config_to_merge),
        dataclass_to_dict_no_defaults(config_with_changes),
    )
    return config_class(**resulting_dict_config)


def merge_dict_configs(
    config_dict: dict[str, typing.Any],
    changes_dict: dict[str, typing.Any],
) -> dict[str, typing.Any]:
    for change_key, change_value in changes_dict.items():
        config_value = config_dict.get(change_key)

        if isinstance(config_value, set):
            if not isinstance(change_value, set):
                raise exceptions.ConfigMergeError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = {*config_value, *change_value}
            continue

        if isinstance(config_value, tuple):
            if not isinstance(change_value, tuple):
                raise exceptions.ConfigMergeError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = (*config_value, *change_value)
            continue

        if isinstance(config_value, list):
            if not isinstance(change_value, list):
                raise exceptions.ConfigMergeError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = [*config_value, *change_value]
            continue

        if isinstance(config_value, dict):
            if not isinstance(change_value, dict):
                raise exceptions.ConfigMergeError(f"Can't merge {config_value} and {change_value}")
            config_dict[change_key] = {**config_value, **change_value}
            continue

        config_dict[change_key] = change_value

    return config_dict


def is_valid_path(maybe_path: str) -> bool:
    return bool(re.fullmatch(VALID_PATH_PATTERN, maybe_path))


def optimize_exclude_paths(
    exclude_endpoints: typing.Iterable[str],
) -> typing.Collection[str]:
    # `in` operator is faster for tuples than for lists
    endpoints_to_ignore: typing.Collection[str] = tuple(exclude_endpoints)

    # 10 is just an empirical value, based of measuring the performance
    # iterating over a tuple of <10 elements is faster than hashing
    if len(endpoints_to_ignore) >= 10:  # noqa: PLR2004
        endpoints_to_ignore = set(endpoints_to_ignore)

    return endpoints_to_ignore
