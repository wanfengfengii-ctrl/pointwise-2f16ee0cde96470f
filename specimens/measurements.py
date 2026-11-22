import re

from archive_core import InputError


_GROUP_WIDTH = 9
_GROUP_BASE = 10 ** _GROUP_WIDTH
_DECIMAL = re.compile(r'(?:0|-?[1-9][0-9]*)')


def require_micrometers(value):
    if type(value) is not int:
        raise InputError('thickness must be an integer in micrometers')
    return value


def encode_micrometers(value):
    value = require_micrometers(value)
    sign = '-' if value < 0 else ''
    magnitude = abs(value)
    groups = []
    # Convert bounded groups so Python's digit limit never rounds or rejects a reading.
    while magnitude >= _GROUP_BASE:
        magnitude, group = divmod(magnitude, _GROUP_BASE)
        groups.append(f'{group:0{_GROUP_WIDTH}d}')
    return sign + str(magnitude) + ''.join(reversed(groups))


def decode_micrometers(value):
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise InputError('invalid stored micrometer value')
    negative = value.startswith('-')
    digits = value[1:] if negative else value
    length = len(digits)
    first_width = length % _GROUP_WIDTH or _GROUP_WIDTH
    magnitude = int(digits[:first_width])
    for offset in range(first_width, length, _GROUP_WIDTH):
        magnitude = magnitude * _GROUP_BASE + int(digits[offset:offset + _GROUP_WIDTH])
    return -magnitude if negative else magnitude
