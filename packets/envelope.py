from dataclasses import dataclass

from archive_core import InputError, PacketError, canonical, read_document, require_fields, sha256_hex, text_key
from packets.manifest import DisclosureManifest, read_manifest


@dataclass(frozen=True)
class FixedEnvelope:
    packet_id: str
    volume_id: str
    manifest: DisclosureManifest
    body: bytes
    wire: bytes


def _payload(volume_id, manifest, body):
    return {'version': 1, 'volume_id': volume_id, 'points': list(manifest.points), 'body': body}


def encode_envelope(volume_id, manifest, body):
    text_key(volume_id, 'volume ID')
    read_manifest(list(manifest.points))
    if type(body) is not dict:
        raise InputError('packet body must be an object')
    payload = _payload(volume_id, manifest, body)
    checksum = sha256_hex(canonical(payload))
    packet_id = 'pkt-' + checksum
    wire = canonical({**payload, 'packet_id': packet_id, 'payload_sha256': checksum})
    return FixedEnvelope(packet_id, volume_id, manifest, canonical(body), wire)


def decode_envelope(wire):
    try:
        fields = ('version', 'volume_id', 'points', 'body', 'packet_id', 'payload_sha256')
        raw = require_fields(read_document(wire), fields)
        if type(raw['version']) is not int or raw['version'] != 1:
            raise InputError('unsupported fixed packet version')
        manifest = read_manifest(raw['points'])
        verified = encode_envelope(raw['volume_id'], manifest, raw['body'])
        if verified.wire != wire:
            raise InputError('fixed packet identity or payload checksum mismatch')
    except InputError as exc:
        raise PacketError(f'invalid fixed packet envelope ({exc})') from exc
    return verified
