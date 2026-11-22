from dataclasses import dataclass

from archive_core import MissingRecord, name_sequence, require_fields
from specimens.identity import source_reference, specimen_key
from specimens.measurements import decode_micrometers, encode_micrometers


@dataclass(frozen=True)
class SpecimenRecord:
    specimen_id: str
    micrometers: int
    source_reference: str

    def to_payload(self):
        return {
            'specimen_id': self.specimen_id,
            'micrometers': encode_micrometers(self.micrometers),
            'source_reference': self.source_reference,
        }

    @classmethod
    def from_payload(cls, payload):
        require_fields(payload, ('specimen_id', 'micrometers', 'source_reference'))
        return cls(specimen_key(payload['specimen_id']),
                   decode_micrometers(payload['micrometers']),
                   source_reference(payload['source_reference']))


def _find_specimen(connection, specimen_id):
    row = connection.execute(
        'SELECT specimen_id, micrometers, source_reference FROM specimens WHERE specimen_id = ?',
        (specimen_id,),
    ).fetchone()
    if row is None:
        return None
    key, reading, reference = row
    return SpecimenRecord(key, decode_micrometers(reading), reference)


def get_specimen(connection, specimen_id):
    specimen_id = specimen_key(specimen_id)
    record = _find_specimen(connection, specimen_id)
    if record is None:
        raise MissingRecord(f'unknown specimen {specimen_id!r}')
    return record


def load_specimens(connection, specimen_ids):
    # Individual lookups also avoid SQLite's bound-parameter limit for large volumes.
    keys = dict.fromkeys(name_sequence(specimen_ids, 'specimen ID'))
    return {key: _find_specimen(connection, key) for key in keys}
