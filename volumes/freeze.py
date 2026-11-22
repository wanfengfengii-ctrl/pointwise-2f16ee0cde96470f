from archive_core import InputError, write_transaction
from specimens.history import load_specimens
from volumes.candidates import bind_candidates
from volumes.draft import VolumeDraft
from volumes.snapshot import make_snapshot
from volumes.store import save_frozen_record


def freeze(connection, draft):
    if not isinstance(draft, VolumeDraft):
        raise InputError('freeze requires a volume draft')
    with write_transaction(connection):
        registrations = load_specimens(connection, draft.specimen_ids)
        candidates = bind_candidates(draft, registrations)
        snapshot = make_snapshot(registrations, candidates)
        save_frozen_record(connection, snapshot.volume_id, snapshot.to_bytes())
    return snapshot
