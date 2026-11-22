import json

from archive_core import InputError, MissingRecord, PacketError, canonical
from packets.envelope import encode_envelope
from packets.issue import issue
from packets.receive import read_received, receive
from tests.fixtures import ArchiveCase, LEGACY_PACKET_ID, LEGACY_VOLUME_ID, SHARED_READINGS, SAMPLES, shared_candidates, table_count


class PacketTests(ArchiveCase):
    def test_disclosure_keeps_allowed_originals_and_hides_private_material(self):
        originals = (*SHARED_READINGS, ('source-only-slide', 97, 'NEVER-HAND-OFF-SLIP'),
                     ('unreferenced-slide', 115, 'UNREFERENCED-SLIP'))
        candidates = {'A': ('r07',), 'B': ('r11',), 'PRIVATE-STATION-C': ('source-only-slide',)}
        frozen = self.frozen(originals, candidates)
        envelope = issue(self.source, frozen.volume_id, ('B', 'A'))
        delivered = receive(self.isolated, envelope.packet_id, envelope.wire)
        self.assertEqual(delivered.envelope.volume_id, frozen.volume_id)
        self.assertEqual(delivered.envelope.manifest.points, ('A', 'B'))
        self.assertEqual(issue(self.source, frozen.volume_id, ('A', 'B')).wire, envelope.wire)
        raw = json.loads(envelope.wire)

        def atoms(value):
            if isinstance(value, dict):
                for key, element in value.items():
                    yield key
                    yield from atoms(element)
            elif isinstance(value, list):
                for element in value:
                    yield from atoms(element)
            else:
                yield value

        values = set(atoms(raw))
        self.assertTrue({'A', 'B', 'r07', 'r11', 'SLIP-07', 'SLIP-11', '7', '11'} <= values)
        private = {'PRIVATE-STATION-C', 'source-only-slide', 'NEVER-HAND-OFF-SLIP', '97', 97,
                   'unreferenced-slide', 'UNREFERENCED-SLIP', '115', 115, 'SLIP-13'}
        self.assertTrue(values.isdisjoint(private), values & private)

    def test_invalid_issue(self):
        frozen = self.frozen(SHARED_READINGS, shared_candidates('r13'))
        with self.assertRaises(MissingRecord):
            issue(self.source, 'vol-unknown', ['A'])
        for invalid in ([], ['unknown'], ['A', 'A'], 'A'):
            with self.subTest(points=invalid), self.assertRaises(InputError):
                issue(self.source, frozen.volume_id, invalid)
        self.assertEqual(table_count(self.source, 'frozen_volumes'), 1)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 0)

    def test_derived_occupancy_differs_with_same_disclosed_originals(self):
        first = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        second = self.delivered(SHARED_READINGS, shared_candidates('r07'), ['A', 'B'])
        self.assertEqual(first.envelope.manifest, second.envelope.manifest)
        first_body = json.loads(first.envelope.body)
        second_body = json.loads(second.envelope.body)
        first_body.pop('volume_id')
        second_body.pop('volume_id')
        self.assertNotEqual(first_body, second_body, 'V3_DERIVED_OCCUPANCY_MISSING')
        self.assertEqual(table_count(self.isolated, 'received_packets'), 2)

    def test_hidden_occupancy_rows_are_bound_and_validated(self):
        packet = self.issued(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        body = json.loads(packet.body)
        self.assertEqual(body['hidden'], [['r13']], 'V3_HIDDEN_OCCUPANCY_BASIS')
        malformed = (
            {'hidden': [['undisclosed-slide']]},
            {'hidden': [[1]]},
            {'hidden': [['r13'], ['r07']]},
            {'hidden': [['r07', 'r07']]},
            {'hidden': 'r13'},
        )
        for patch in malformed:
            with self.subTest(patch=patch):
                wrong = encode_envelope(packet.volume_id, packet.manifest, {**body, **patch})
                with self.assertRaises(PacketError):
                    receive(self.isolated, wrong.packet_id, wrong.wire)
        occupancy_less = {key: value for key, value in body.items() if key != 'hidden'}
        occupancy_less['kind'] = 'disclosed-candidates-v1'
        wrong = encode_envelope(packet.volume_id, packet.manifest, occupancy_less)
        with self.assertRaises(PacketError):
            receive(self.isolated, wrong.packet_id, wrong.wire)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 0)
        self.assertEqual(self.signing_count(), (0, 0))

    def test_wrong_expected_packet_is_rejected(self):
        first = self.issued(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        second = self.issued(SHARED_READINGS, shared_candidates('r07'), ['A', 'B'])
        with self.assertRaises(PacketError):
            receive(self.isolated, first.packet_id, second.wire)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 0)
        self.assertEqual(self.signing_count(), (0, 0))
        accepted = receive(self.isolated, second.packet_id, second.wire)
        self.assertEqual(accepted.envelope.packet_id, second.packet_id)

    def test_tampered_body_and_malformed_bound_bodies_are_rejected(self):
        packet = self.issued(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        tampered = json.loads(packet.wire)
        tampered['body']['volume_id'] = 'vol-wrong'
        with self.assertRaises(PacketError):
            receive(self.isolated, packet.packet_id, canonical(tampered))
        invalid_bodies = (
            {**json.loads(packet.body), 'volume_id': 'vol-wrong'},
            {**json.loads(packet.body), 'points': ['A']},
            {'kind': 'unknown-format', 'volume_id': packet.volume_id, 'points': ['A', 'B']},
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                wrong = encode_envelope(packet.volume_id, packet.manifest, body)
                with self.assertRaises(PacketError):
                    receive(self.isolated, wrong.packet_id, wrong.wire)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 0)
        self.assertEqual(self.signing_count(), (0, 0))

    def test_receive_replay_and_reopen(self):
        packet = self.issued(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        first = receive(self.isolated, packet.packet_id, packet.wire)
        self.reopen_isolated()
        replay = receive(self.isolated, packet.packet_id, packet.wire)
        self.assertEqual(first, replay)
        self.assertEqual(read_received(self.isolated, replay.intake_id).envelope.wire, packet.wire)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 1)

    def test_recorded_complete_legacy_packet(self):
        original = (SAMPLES / 'legacy_packet.json').read_bytes()
        with self.assertRaises(PacketError):
            receive(self.isolated, 'pkt-other', original)
        corrupted = original.replace(b'M-OLD-17', b'M-OLD-77')
        with self.assertRaises(PacketError):
            receive(self.isolated, LEGACY_PACKET_ID, corrupted)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 0)
        delivered = self.accept_legacy()
        self.source.close()
        self.reopen_isolated()
        reloaded = read_received(self.isolated, delivered.intake_id)
        self.assertEqual(reloaded.envelope.wire, original)
        self.assertEqual(reloaded.envelope.packet_id, LEGACY_PACKET_ID)
        self.assertEqual(reloaded.envelope.volume_id, LEGACY_VOLUME_ID)
        self.assertEqual(reloaded.envelope.manifest.points, ('A',))
