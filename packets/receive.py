from dataclasses import dataclass

from archive_core import MissingRecord, PacketError, canonical, content_id, enable_foreign_keys, text_key, write_transaction
from packets.envelope import FixedEnvelope, decode_envelope
from packets.evidence import PacketEvidence, decode_evidence


@dataclass(frozen=True)
class ReceivedPacket:
    intake_id: str
    envelope: FixedEnvelope
    evidence: PacketEvidence


def initialize_intake(connection):
    enable_foreign_keys(connection)
    connection.execute('''
        CREATE TABLE IF NOT EXISTS received_packets (
            intake_id TEXT PRIMARY KEY NOT NULL,
            packet_id TEXT UNIQUE NOT NULL,
            wire BLOB NOT NULL
        )
    ''')


def _inspect(wire, expected_packet_id):
    envelope = decode_envelope(wire)
    if envelope.packet_id != expected_packet_id:
        raise PacketError('incoming packet does not match the expected packet ID')
    evidence = decode_evidence(envelope.body)
    if evidence.volume_id != envelope.volume_id or evidence.manifest != envelope.manifest:
        raise PacketError('body does not match the envelope volume and disclosure list')
    intake_id = content_id('in', canonical([envelope.packet_id]))
    return ReceivedPacket(intake_id, envelope, evidence)


def read_received(connection, intake_id):
    intake_id = text_key(intake_id, 'intake ID')
    row = connection.execute(
        'SELECT packet_id, wire FROM received_packets WHERE intake_id = ?', (intake_id,),
    ).fetchone()
    if row is None:
        raise MissingRecord(f'unknown intake {intake_id!r}')
    packet_id, wire = row
    received = _inspect(wire, packet_id)
    if received.intake_id != intake_id:
        raise PacketError('stored intake ID disagrees with the fixed packet')
    return received


def receive(connection, expected_packet_id, wire):
    received = _inspect(wire, expected_packet_id)
    with write_transaction(connection):
        connection.execute('''
            INSERT INTO received_packets (intake_id, packet_id, wire) VALUES (?, ?, ?)
            ON CONFLICT(intake_id) DO NOTHING
        ''', (received.intake_id, received.envelope.packet_id, wire))
        stored = read_received(connection, received.intake_id)
        if stored.envelope.wire != wire:
            raise PacketError('incoming packet conflicts with the original intake')
    return stored
