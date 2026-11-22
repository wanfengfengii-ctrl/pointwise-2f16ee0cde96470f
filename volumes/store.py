from archive_core import ConflictError, MissingRecord, text_key
from specimens.register import initialize_specimens


def initialize_source(connection):
    initialize_specimens(connection)
    connection.execute('''
        CREATE TABLE IF NOT EXISTS frozen_volumes (
            volume_id TEXT PRIMARY KEY NOT NULL,
            snapshot BLOB NOT NULL
        )
    ''')


def save_frozen_record(connection, volume_id, snapshot):
    connection.execute('''
        INSERT INTO frozen_volumes (volume_id, snapshot) VALUES (?, ?)
        ON CONFLICT(volume_id) DO NOTHING
    ''', (volume_id, snapshot))
    if load_frozen_record(connection, volume_id) != snapshot:
        raise ConflictError(f'conflicting snapshot for {volume_id!r}')


def load_frozen_record(connection, volume_id):
    volume_id = text_key(volume_id, 'volume ID')
    row = connection.execute(
        'SELECT snapshot FROM frozen_volumes WHERE volume_id = ?', (volume_id,),
    ).fetchone()
    if row is None:
        raise MissingRecord(f'unknown frozen volume {volume_id!r}')
    return row[0]
