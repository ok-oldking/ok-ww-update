def get_first_item(lst, default=None):
    return next(iter(lst), default) if lst is not None else default


def safe_get(lst, idx, default=None):
    try:
        return lst[idx]
    except IndexError:
        return default


def find_index_in_list(my_list, target_string, default_index=-1):
    try:
        index = my_list.index(target_string)
        return index
    except ValueError:
        return default_index
