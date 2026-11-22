from packets.envelope import encode_envelope
from packets.evidence import build_evidence, encode_evidence
from packets.manifest import build_manifest
from volumes.snapshot import read_frozen_volume


def issue(connection, volume_id, disclosed_points):
    volume = read_frozen_volume(connection, volume_id)
    manifest = build_manifest(volume.candidates, disclosed_points)
    evidence = build_evidence(volume, manifest)
    return encode_envelope(volume.volume_id, manifest, encode_evidence(evidence))
