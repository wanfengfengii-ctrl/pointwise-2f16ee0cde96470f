from archive_core import ConflictError, InputError, MissingRecord
from specimens.history import get_specimen, load_specimens
from specimens.register import register
from tests.fixtures import ArchiveCase, table_count
from volumes.draft import create_draft
from volumes.freeze import freeze
from volumes.snapshot import read_frozen_volume
from volumes.store import initialize_source


class VolumeTests(ArchiveCase):
    def test_equal_readings_keep_originals(self):
        frozen = self.frozen((('left-7', 7, 'SLIP-L'), ('right-7', 7, 'SLIP-R')),
                             {'A': ['right-7', 'left-7', 'right-7'], 'B': ['right-7']})
        snapshot = read_frozen_volume(self.source, frozen.volume_id)
        self.assertEqual(snapshot.candidates, {'A': ('left-7', 'right-7'), 'B': ('right-7',)})
        self.assertEqual([(row.specimen_id, row.micrometers, row.source_reference)
                          for row in snapshot.specimens.values()],
                         [('left-7', 7, 'SLIP-L'), ('right-7', 7, 'SLIP-R')])

    def test_invalid_measurements(self):
        for bad in (None, True, False, 7.0, '7'):
            with self.subTest(value=bad), self.assertRaises(InputError):
                register(self.source, 'foil-7', bad, 'SLIP-07')
        for bad_key, bad_slip in (('', 'SLIP-07'), ('foil-7', ''), (9, 'SLIP-07')):
            with self.subTest(key=bad_key, slip=bad_slip), self.assertRaises(InputError):
                register(self.source, bad_key, 7, bad_slip)
        self.assertEqual(table_count(self.source, 'specimens'), 0)

    def test_registration_replay_and_conflict(self):
        original = register(self.source, 'foil-7', 7, 'SLIP-07')
        self.assertEqual(register(self.source, 'foil-7', 7, 'SLIP-07'), original)
        for reading, slip in ((7, 'OTHER-SLIP'), (8, 'SLIP-07')):
            with self.subTest(reading=reading, slip=slip), self.assertRaises(ConflictError):
                register(self.source, 'foil-7', reading, slip)
        self.assertEqual(get_specimen(self.source, 'foil-7'), original)
        self.assertEqual(table_count(self.source, 'specimens'), 1)
        self.assertEqual(load_specimens(self.source, ['foil-7', 'foil-7 ']),
                         {'foil-7': original, 'foil-7 ': None})
        with self.assertRaises(MissingRecord):
            get_specimen(self.source, 'foil-7 ')

    def test_source_reinitialize(self):
        frozen = self.frozen((('working-piece', 61, 'LOCAL-SLIP'),), {'Station Q': ['working-piece']})
        initialize_source(self.source)
        self.source.close()
        self.source = self.connect(self.source_path)
        initialize_source(self.source)
        self.assertEqual(table_count(self.source, 'specimens'), 1)
        self.assertEqual(table_count(self.source, 'frozen_volumes'), 1)
        self.assertEqual(get_specimen(self.source, 'working-piece').source_reference, 'LOCAL-SLIP')
        self.assertEqual(read_frozen_volume(self.source, frozen.volume_id), frozen)

    def test_invalid_candidate_preserves_frozen_volume(self):
        original = self.frozen((('foil', 7, 'SLIP-07'),), {'A': ['foil']})
        register(self.source, 'other-volume-foil', 8, 'OTHER-SLIP')
        invalid_drafts = (
            create_draft(['foil', 'undelivered'], {'A': ['foil', 'undelivered']}),
            create_draft(['foil'], {'A': ['foil', 'other-volume-foil']}),
        )
        for draft in invalid_drafts:
            with self.subTest(draft=draft), self.assertRaises(InputError):
                freeze(self.source, draft)
            self.assertEqual(table_count(self.source, 'frozen_volumes'), 1)
            self.assertEqual(read_frozen_volume(self.source, original.volume_id), original)

    def test_later_freeze_keeps_original_snapshot(self):
        old = self.frozen((('foil-7', 7, 'SLIP-07'),), {'A': ['foil-7']})
        register(self.source, 'foil-11', 11, 'SLIP-11')
        updated = freeze(self.source, create_draft(['foil-7', 'foil-11'], {'A': ['foil-11']}))
        replayed = freeze(self.source, create_draft(['foil-11', 'foil-7', 'foil-11'], {'A': ['foil-11']}))
        self.assertNotEqual(old.volume_id, updated.volume_id)
        self.assertEqual(replayed, updated)
        self.assertEqual(table_count(self.source, 'frozen_volumes'), 2)
        original = read_frozen_volume(self.source, old.volume_id)
        self.assertEqual(original.candidates['A'], ('foil-7',))
        self.assertEqual(original.specimens['foil-7'].micrometers, 7)
        self.assertEqual(original.specimens['foil-7'].source_reference, 'SLIP-07')
        self.assertEqual(read_frozen_volume(self.source, updated.volume_id).candidates['A'], ('foil-11',))

    def test_draft_requires_candidate_table_but_preserves_empty_point(self):
        for absent in (None, {}):
            with self.subTest(value=absent), self.assertRaises(InputError):
                create_draft([], absent)
        with self.assertRaises(InputError):
            create_draft([], {'A': None})
        frozen = freeze(self.source, create_draft([], {'A': []}))
        self.assertEqual(read_frozen_volume(self.source, frozen.volume_id).candidates, {'A': ()})
