def split_find_contains(value: str, target: object, sep: str, match: bool) -> bool:
    ss = value.split(sep)
    is_contains = False

    for s in ss:
        if s in str(target):
            is_contains = True
            break

    return is_contains and match
