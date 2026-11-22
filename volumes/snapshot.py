from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from archive_core import InputError, ReconciliationError, canonical, content_id, read_document, require_fields
from specimens.history import SpecimenRecord
from volumes.candidates import bind_candidates
from volumes.draft import create_draft
from volumes.store import load_frozen_record


def _snapshot_bytes(specimens, candidates):
    return canonical({
        'specimens': {key: record.to_payload() for key, record in specimens.items()},
        'candidates': {point: list(choices) for point, choices in candidates.items()},
    })


@dataclass(frozen=True)
class FrozenVolume:
    volume_id: str
    specimens: Mapping[str, SpecimenRecord]
    candidates: Mapping[str, tuple[str, ...]]

    def to_bytes(self):
        return _snapshot_bytes(self.specimens, self.candidates)


def make_snapshot(specimens, candidates):
    draft = create_draft(specimens.keys(), candidates)
    edges = bind_candidates(draft, specimens)
    originals = {}
    for key in draft.specimen_ids:
        record = specimens[key]
        if not isinstance(record, SpecimenRecord) or record.specimen_id != key:
            raise InputError(f'invalid measurement record for {key!r}')
        originals[key] = record
    raw = _snapshot_bytes(originals, edges)
    return FrozenVolume(content_id('vol', raw), MappingProxyType(originals), MappingProxyType(edges))


def read_frozen_volume(connection, volume_id):
    raw = load_frozen_record(connection, volume_id)
    try:
        payload = require_fields(read_document(raw), ('specimens', 'candidates'))
        if type(payload['specimens']) is not dict:
            raise InputError('invalid frozen specimen table')
        specimens = {key: SpecimenRecord.from_payload(record)
                     for key, record in payload['specimens'].items()}
        snapshot = make_snapshot(specimens, payload['candidates'])
        if snapshot.volume_id != volume_id or snapshot.to_bytes() != raw:
            raise InputError('frozen snapshot does not match its volume ID')
    except InputError as exc:
        raise ReconciliationError(f'cannot read frozen volume {volume_id!r}') from exc
    return snapshot
