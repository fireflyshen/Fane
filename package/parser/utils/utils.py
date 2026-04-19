def split_find_contains(str: str, target: str, sep: str, match: bool) -> bool:
    ss = str.split(sep)
    is_contains = False

    for s in ss:
        if s in target:
            is_contains = True
            break

    return is_contains and match
