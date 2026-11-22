from archive_core import ConflictError, enable_foreign_keys, write_transaction
from specimens.history import SpecimenRecord, get_specimen
from specimens.identity import source_reference, specimen_key
from specimens.measurements import encode_micrometers, require_micrometers


def initialize_specimens(connection):
    enable_foreign_keys(connection)
    connection.execute('''
        CREATE TABLE IF NOT EXISTS specimens (
            specimen_id TEXT PRIMARY KEY NOT NULL,
            micrometers TEXT NOT NULL,
            source_reference TEXT NOT NULL
        )
    ''')


def register(connection, specimen_id, micrometers, original_reference):
    proposed = SpecimenRecord(specimen_key(specimen_id), require_micrometers(micrometers),
                              source_reference(original_reference))
    with write_transaction(connection):
        connection.execute('''
            INSERT INTO specimens (specimen_id, micrometers, source_reference)
            VALUES (?, ?, ?) ON CONFLICT(specimen_id) DO NOTHING
        ''', (proposed.specimen_id, encode_micrometers(proposed.micrometers),
              proposed.source_reference))
        stored = get_specimen(connection, proposed.specimen_id)
        if stored != proposed:
            raise ConflictError(f'conflicting registration for {proposed.specimen_id!r}')
    return stored
