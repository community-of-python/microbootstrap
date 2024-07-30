import typing

import pytest

from microbootstrap import exceptions, helpers


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
