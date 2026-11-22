from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from archive_core import InputError, PacketError, name_sequence, read_document, require_fields, text_key
from packets.manifest import DisclosureManifest, read_manifest
from specimens.history import SpecimenRecord
from volumes.snapshot import FrozenVolume


@dataclass(frozen=True)
class PacketEvidence:
    volume_id: str
    manifest: DisclosureManifest
    visible: Mapping[str, str]
    candidates: Mapping[str, tuple[str, ...]]
    originals: Mapping[str, SpecimenRecord]


def _immutable_evidence(volume_id, manifest, candidates, originals):
    visible = {point: point for point in manifest.points}
    return PacketEvidence(volume_id, manifest, MappingProxyType(visible),
                          MappingProxyType(dict(candidates)), MappingProxyType(dict(originals)))


def build_evidence(volume: FrozenVolume, manifest: DisclosureManifest):
    candidates = {point: volume.candidates[point] for point in manifest.points}
    specimen_ids = {key for choices in candidates.values() for key in choices}
    originals = {key: volume.specimens[key] for key in sorted(specimen_ids)}
    return _immutable_evidence(volume.volume_id, manifest, candidates, originals)


def encode_evidence(evidence):
    return {
        'kind': 'disclosed-candidates-v1',
        'volume_id': evidence.volume_id,
        'points': list(evidence.manifest.points),
        'candidates': {point: list(choices) for point, choices in evidence.candidates.items()},
        'originals': {key: record.to_payload() for key, record in evidence.originals.items()},
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


def decode_evidence(raw):
    try:
        body = read_document(raw)
        kind = body.get('kind') if type(body) is dict else None
        fields = ('kind', 'volume_id', 'points', 'candidates', 'originals')
        if kind == 'complete-v0':
            require_fields(body, (*fields, 'complete'))
            if body['complete'] is not True:
                raise InputError('old packet requires complete disclosure')
        elif kind == 'disclosed-candidates-v1':
            require_fields(body, fields)
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
    except InputError as exc:
        raise PacketError(f'invalid fixed packet evidence ({exc})') from exc
    return _immutable_evidence(volume_id, manifest, candidates, originals)
