from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from archive_core import InputError, PacketError, name_sequence, read_document, require_fields, text_key
from packets.manifest import DisclosureManifest, read_manifest
from specimens.history import SpecimenRecord
from volumes.snapshot import FrozenVolume


@dataclass(frozen=True)
class HiddenPoint:
    """An undisclosed measuring point, known to the night shift only by its canonical row."""
    index: int


@dataclass(frozen=True)
class HiddenSpecimen:
    """A specimen referenced only by undisclosed points; identity and reading stay on station."""
    index: int


@dataclass(frozen=True)
class PacketEvidence:
    volume_id: str
    manifest: DisclosureManifest
    visible: Mapping[str, str]
    candidates: Mapping
    originals: Mapping[str, SpecimenRecord]


def _immutable_evidence(volume_id, manifest, candidates, originals):
    visible = {point: point for point in manifest.points}
    return PacketEvidence(volume_id, manifest, MappingProxyType(visible),
                          MappingProxyType(dict(candidates)), MappingProxyType(dict(originals)))


def _entry_order(entry):
    if isinstance(entry, HiddenSpecimen):
        return (0, entry.index)
    return (1, entry)


def _row_order(row):
    return tuple(_entry_order(entry) for entry in row)


def _graph_with_hidden(candidates, rows):
    graph = dict(candidates)
    for index, row in enumerate(rows):
        graph[HiddenPoint(index)] = row
    return graph


def build_evidence(volume: FrozenVolume, manifest: DisclosureManifest):
    candidates = {point: volume.candidates[point] for point in manifest.points}
    visible_specimens = {key for choices in candidates.values() for key in choices}
    originals = {key: volume.specimens[key] for key in sorted(visible_specimens)}
    hidden_points = sorted(point for point in volume.candidates if point not in candidates)
    dedicated = sorted({
        specimen for point in hidden_points for specimen in volume.candidates[point]
    }.difference(visible_specimens))
    slots = {specimen: HiddenSpecimen(index) for index, specimen in enumerate(dedicated)}
    rows = [tuple(sorted((slots.get(specimen, specimen) for specimen in volume.candidates[point]),
                         key=_entry_order))
            for point in hidden_points]
    rows.sort(key=_row_order)
    return _immutable_evidence(volume.volume_id, manifest,
                               _graph_with_hidden(candidates, rows), originals)


def _wire_entry(entry):
    if isinstance(entry, HiddenSpecimen):
        return entry.index
    return text_key(entry, 'hidden specimen reference')


def encode_evidence(evidence):
    hidden_keys = sorted((key for key in evidence.candidates if isinstance(key, HiddenPoint)),
                         key=lambda key: key.index)
    return {
        'kind': 'disclosed-candidates-v2',
        'volume_id': evidence.volume_id,
        'points': list(evidence.manifest.points),
        'candidates': {point: list(evidence.candidates[point])
                       for point in evidence.manifest.points},
        'originals': {key: record.to_payload() for key, record in evidence.originals.items()},
        'hidden': [[_wire_entry(entry) for entry in evidence.candidates[key]]
                   for key in hidden_keys],
    }


def _read_candidates(raw):
    if type(raw) is not dict:
        raise InputError('invalid packet candidate table')
    candidates = {}
    for point, choices in raw.items():
        point = text_key(point, 'candidate point')
        if type(choices) is not list:
            raise InputError('candidate choices must be a JSON array')
        specimen_ids = name_sequence(choices, 'candidate specimen ID')
        if specimen_ids != tuple(sorted(set(specimen_ids))):
            raise InputError('invalid canonical candidate list')
        candidates[point] = specimen_ids
    return candidates


def _read_originals(raw):
    if type(raw) is not dict:
        raise InputError('invalid packet originals table')
    originals = {text_key(key, 'specimen ID'): SpecimenRecord.from_payload(record)
                 for key, record in raw.items()}
    if any(key != record.specimen_id for key, record in originals.items()):
        raise InputError('specimen references do not match their originals')
    return originals


def _read_hidden(raw, visible_specimens):
    if type(raw) is not list:
        raise InputError('hidden obligations must be a JSON array')
    rows = []
    slots = set()
    for raw_row in raw:
        if type(raw_row) is not list:
            raise InputError('each hidden obligation must be a JSON array')
        row = []
        for entry in raw_row:
            if type(entry) is str:
                if text_key(entry, 'hidden specimen reference') not in visible_specimens:
                    raise InputError('hidden obligation names an undisclosed specimen')
                row.append(entry)
            elif type(entry) is int and entry >= 0:
                row.append(HiddenSpecimen(entry))
                slots.add(entry)
            else:
                raise InputError('hidden obligation entries must be specimen IDs or slots')
        if len(set(row)) != len(row) or row != sorted(row, key=_entry_order):
            raise InputError('hidden obligation entries are not canonical')
        rows.append(tuple(row))
    if rows != sorted(rows, key=_row_order):
        raise InputError('hidden obligations are not in canonical order')
    if slots != set(range(len(slots))):
        raise InputError('hidden specimen slots must be dense from zero')
    return tuple(rows)


def decode_evidence(raw):
    try:
        body = read_document(raw)
        kind = body.get('kind') if type(body) is dict else None
        fields = ('kind', 'volume_id', 'points', 'candidates', 'originals')
        if kind == 'complete-v0':
            require_fields(body, (*fields, 'complete'))
            if body['complete'] is not True:
                raise InputError('old packet requires complete disclosure')
            rows = ()
        elif kind == 'disclosed-candidates-v2':
            require_fields(body, (*fields, 'hidden'))
            rows = None
        else:
            raise InputError('unsupported packet evidence')
        volume_id = text_key(body['volume_id'], 'evidence volume ID')
        manifest = read_manifest(body['points'])
        candidates = _read_candidates(body['candidates'])
        if set(candidates) != set(manifest.points):
            raise InputError('candidate rows do not match the disclosure list')
        originals = _read_originals(body['originals'])
        required_originals = {key for choices in candidates.values() for key in choices}
        if set(originals) != required_originals:
            raise InputError('packet originals do not match disclosed candidate references')
        if rows is None:
            rows = _read_hidden(body['hidden'], frozenset(required_originals))
    except InputError as exc:
        raise PacketError(f'invalid fixed packet evidence ({exc})') from exc
    return _immutable_evidence(volume_id, manifest, _graph_with_hidden(candidates, rows), originals)
