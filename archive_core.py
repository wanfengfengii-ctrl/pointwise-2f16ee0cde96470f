import hashlib
import json
from collections.abc import Mapping
from contextlib import contextmanager


class ArchiveError(ValueError):
    pass


class InputError(ArchiveError):
    pass


class ConflictError(ArchiveError):
    pass


class MissingRecord(ArchiveError):
    pass


class PacketError(ArchiveError):
    pass


class RequestError(ArchiveError):
    pass


class SignError(ArchiveError):
    pass


class ReconciliationError(ArchiveError):
    pass


class StorageError(ArchiveError):
    pass


def text_key(value, label):
    if type(value) is not str or not value:
        raise InputError(f'{label} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise InputError(f'{label} must contain valid Unicode') from exc
    return value


def name_sequence(values, label):
    if isinstance(values, (str, bytes, bytearray, Mapping)):
        raise InputError(f'{label} must be a collection of names')
    try:
        names = iter(values)
    except TypeError as exc:
        raise InputError(f'{label} must be a collection of names') from exc
    return tuple(text_key(name, label) for name in names)


def require_fields(document, names):
    if type(document) is not dict or set(document) != set(names):
        raise InputError(f'expected object fields {sorted(names)!r}')
    return document


def canonical(document):
    return json.dumps(document, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def read_document(raw):
    if type(raw) is not bytes:
        raise InputError('expected canonical JSON bytes')
    try:
        document = json.loads(raw)
        if canonical(document) != raw:
            raise InputError('JSON is not in canonical form')
    except (ValueError, RecursionError) as exc:
        raise InputError('invalid canonical JSON') from exc
    return document


def sha256_hex(raw):
    return hashlib.sha256(raw).hexdigest()


def content_id(prefix, raw):
    return prefix + '-' + sha256_hex(raw)


def require_idle(connection):
    if connection.in_transaction:
        raise StorageError('entry point requires a connection outside a transaction')


def enable_foreign_keys(connection):
    require_idle(connection)
    connection.execute('PRAGMA foreign_keys = ON')


@contextmanager
def write_transaction(connection):
    require_idle(connection)
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
