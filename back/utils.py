from typing import List

import numpy as np


def is_int(key) -> bool:
    if isinstance(key, int) or isinstance(key, str) and key.isdigit():
        return True


def is_float(key) -> bool:
    if isinstance(key, float):
        return True


def is_int_or_raise(key) -> bool:
    if is_int(key):
        return True
    raise ValueError("'{}' is not an integer value.".format(key))


def is_float_or_raise(key) -> bool:
    if is_float(key):
        return True
    raise ValueError("'{}' is not a float value.".format(key))


def list_bitwise_or(ints: List[int]) -> int:
    res = 0
    for i in ints:
        res |= i
    return res


def square_poly(v: float, k0: float, k1: float, k2: float) -> float:
    return k0 + k1 * v + k2 * v ** 2


def square_poly_array(arr: np.ndarray, k0: float, k1: float, k2: float) -> float:
    return k0 + k1 * arr + k2 * arr ** 2


def cubic_poly(v: float, k0: float, k1: float, k2: float, k3: float) -> float:
    return k0 + k1 * v + k2 * v ** 2 + k3 * v ** 3


def cubic_poly_array(arr: np.ndarray, k0: float, k1: float, k2: float, k3: float) -> np.ndarray:
    return k0 + k1 * arr + k2 * arr ** 2 + k3 * arr ** 3


if __name__ == '__main__':
    pass
