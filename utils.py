import sys


def is_int(key) -> bool:
    if isinstance(key, int) or isinstance(key, str) and key.isdigit():
        return True


def is_int_or_raise(key) -> bool:
    if is_int(key):
        return True
    raise ValueError("'{}' is not an integer value.".format(key))


def reset_cursor():
    """Reset the cursor in the terminal window."""
    sys.stdout.write('\033[1;1H')


def clear_eol():
    """Clear all characters to the end of the line."""
    sys.stdout.write('\x1b[2K')
