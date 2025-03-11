import dataclasses
import typing

import pydantic
import pytest

from microbootstrap import exceptions, helpers
from microbootstrap.helpers import optimize_exclude_paths


@pytest.mark.parametrize(
    ("first_dict", "second_dict", "result", "is_error"),
    [
        ({"value": 1}, {"value": 2}, {"value": 2}, False),
        ({"value": 1, "value2": 2}, {"value": 1, "value2": 3}, {"value": 1, "value2": 3}, False),
        ({"value": 1}, {"value2": 1}, {"value": 1, "value2": 1}, False),
        ({"array": [1, 2]}, {"array": [3, 4]}, {"array": [1, 2, 3, 4]}, False),
        ({"tuple": (1, 2)}, {"tuple": (2, 3)}, {"tuple": (1, 2, 2, 3)}, False),
        ({"set": {1, 2}}, {"set": {2, 3}}, {"set": {1, 2, 3}}, False),
        ({"dict": {"value": 1}}, {"dict": {"value": 1}}, {"dict": {"value": 1}}, False),
        ({"dict": {"value": 1}}, {"dict": {"value": 2}}, {"dict": {"value": 2}}, False),
        (
            {"dict": {"value": 1, "value2": 2, "value4": 4}},
            {"dict": {"value": 5, "value2": 3, "value3": 2}},
            {"dict": {"value": 5, "value2": 3, "value3": 2, "value4": 4}},
            False,
        ),
        ({"array": [1, 2]}, {"array": {"val": 1}}, {}, True),
        ({"tuple": (2, 3)}, {"tuple": [1, 2]}, {}, True),
        ({"dict": {"value": 1}}, {"dict": [1, 2]}, {}, True),
        ({"set": {1, 2}}, {"set": [1, 2]}, {}, True),
    ],
)
def test_merge_config_dicts(
    first_dict: dict[str, typing.Any],
    second_dict: dict[str, typing.Any],
    result: dict[str, typing.Any],
    is_error: bool,
) -> None:
    if is_error:
        with pytest.raises(exceptions.ConfigMergeError):
            helpers.merge_dict_configs(first_dict, second_dict)
    else:
        assert result == helpers.merge_dict_configs(first_dict, second_dict)


class PydanticConfig(pydantic.BaseModel):
    string_field: str
    array_field: list[typing.Any] = pydantic.Field(default_factory=list)
    dict_field: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


@dataclasses.dataclass
class InnerDataclass:
    string_field: str


@pytest.mark.parametrize(
    ("first_model", "second_model", "result"),
    [
        (
            PydanticConfig(string_field="value1"),
            PydanticConfig(string_field="value2"),
            PydanticConfig(string_field="value2"),
        ),
        (
            PydanticConfig(string_field="value1", array_field=[1]),
            PydanticConfig(string_field="value2", array_field=[2]),
            PydanticConfig(string_field="value2", array_field=[1, 2]),
        ),
        (
            PydanticConfig(string_field="value1", dict_field={"value1": 1}),
            PydanticConfig(string_field="value2", dict_field={"value2": 2}),
            PydanticConfig(string_field="value2", dict_field={"value1": 1, "value2": 2}),
        ),
        (
            PydanticConfig(string_field="value1", array_field=[1, 2], dict_field={"value1": 1, "value3": 3}),
            PydanticConfig(string_field="value2", array_field=[1, 3], dict_field={"value2": 2, "value3": 4}),
            PydanticConfig(
                string_field="value2",
                array_field=[1, 2, 1, 3],
                dict_field={"value1": 1, "value2": 2, "value3": 4},
            ),
        ),
        (
            PydanticConfig(string_field="value1", array_field=[1, 2], dict_field={"value1": 1, "value3": 3}),
            PydanticConfig(
                string_field="value2",
                array_field=[InnerDataclass(string_field="hi")],
                dict_field={"value1": 1, "value2": 2, "value3": InnerDataclass(string_field="there")},
            ),
            PydanticConfig(
                string_field="value2",
                array_field=[1, 2, InnerDataclass(string_field="hi")],
                dict_field={"value1": 1, "value2": 2, "value3": InnerDataclass(string_field="there")},
            ),
        ),
    ],
)
def test_merge_pydantic_configs(
    first_model: PydanticConfig,
    second_model: PydanticConfig,
    result: PydanticConfig,
) -> None:
    assert result == helpers.merge_pydantic_configs(first_model, second_model)


@dataclasses.dataclass
class DataclassConfig:
    string_field: str
    array_field: list[typing.Any] = dataclasses.field(default_factory=list)
    dict_field: dict[str, typing.Any] = dataclasses.field(default_factory=dict)


@pytest.mark.parametrize(
    ("first_class", "second_class", "result"),
    [
        (
            DataclassConfig(string_field="value1"),
            DataclassConfig(string_field="value2"),
            DataclassConfig(string_field="value2"),
        ),
        (
            DataclassConfig(string_field="value1", array_field=[1]),
            DataclassConfig(string_field="value2", array_field=[2]),
            DataclassConfig(string_field="value2", array_field=[1, 2]),
        ),
        (
            DataclassConfig(string_field="value1", dict_field={"value1": 1}),
            DataclassConfig(string_field="value2", dict_field={"value2": 2}),
            DataclassConfig(string_field="value2", dict_field={"value1": 1, "value2": 2}),
        ),
        (
            DataclassConfig(string_field="value1", array_field=[1, 2], dict_field={"value1": 1, "value3": 3}),
            DataclassConfig(string_field="value2", array_field=[1, 3], dict_field={"value2": 2, "value3": 4}),
            DataclassConfig(
                string_field="value2",
                array_field=[1, 2, 1, 3],
                dict_field={"value1": 1, "value2": 2, "value3": 4},
            ),
        ),
    ],
)
def test_merge_dataclasses_configs(
    first_class: DataclassConfig,
    second_class: DataclassConfig,
    result: DataclassConfig,
) -> None:
    assert result == helpers.merge_dataclasses_configs(first_class, second_class)


@pytest.mark.parametrize(
    "exclude_paths",
    [
        ["path"],
        ["path"] * 11,
    ],
)
def test_optimize_exclude_paths(exclude_paths: list[str]) -> None:
    optimize_exclude_paths(exclude_paths)
