import typing


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
