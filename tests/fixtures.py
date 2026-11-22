import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from packets.issue import issue
from packets.receive import receive
from reports.store import initialize_isolated
from specimens.register import register
from volumes.draft import create_draft
from volumes.freeze import freeze
from volumes.store import initialize_source


SAMPLES = Path(__file__).resolve().parent.parent / 'samples'
LEGACY_PACKET_ID = 'pkt-2e04c771e3d7a493822b143ff225bf76ca151a8da21fd57fa2ecbb8026eb6c4e'
LEGACY_VOLUME_ID = 'vol-c55e04d4b44e7a06280544da744949f53595dbca8e442e4a3983767b513791fb'
SHARED_READINGS = (('r07', 7, 'SLIP-07'), ('r11', 11, 'SLIP-11'), ('r13', 13, 'SLIP-13'))


def shared_candidates(hidden=None):
    choices = ('r07', 'r11', 'r13')
    candidates = {'A': choices, 'B': choices}
    if hidden is not None:
        candidates['C'] = (hidden,)
    return candidates


def table_count(connection, table):
    if table not in {'specimens', 'frozen_volumes', 'received_packets', 'reports', 'first_receipts'}:
        raise ValueError('unknown fixture table')
    return connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='retained-specimens-test-')
        self.addCleanup(directory.cleanup)
        self.source_path = Path(directory.name) / 'source.sqlite'
        self.isolated_path = Path(directory.name) / 'isolated.sqlite'
        self.source = self.connect(self.source_path)
        self.isolated = self.connect(self.isolated_path)
        initialize_source(self.source)
        initialize_isolated(self.isolated)

    def connect(self, path):
        connection = sqlite3.connect(path)
        self.addCleanup(connection.close)
        return connection

    def frozen(self, originals, candidates):
        specimen_ids = [register(self.source, *row).specimen_id for row in originals]
        return freeze(self.source, create_draft(specimen_ids, candidates))

    def issued(self, originals, candidates, disclosed):
        frozen = self.frozen(originals, candidates)
        return issue(self.source, frozen.volume_id, disclosed)

    def delivered(self, originals, candidates, disclosed):
        envelope = self.issued(originals, candidates, disclosed)
        return receive(self.isolated, envelope.packet_id, envelope.wire)

    def accept_legacy(self):
        return receive(self.isolated, LEGACY_PACKET_ID, (SAMPLES / 'legacy_packet.json').read_bytes())

    def reopen_isolated(self):
        self.isolated.close()
        self.isolated = self.connect(self.isolated_path)
        initialize_isolated(self.isolated)

    def signing_count(self, connection=None):
        db = self.isolated if connection is None else connection
        return table_count(db, 'reports'), table_count(db, 'first_receipts')

    def install_deferred_commit_failure(self):
        self.isolated.executescript('''
            CREATE TABLE commit_gate (gate_id INTEGER PRIMARY KEY);
            CREATE TABLE commit_gate_checks (
                receipt_id TEXT NOT NULL,
                gate_id INTEGER NOT NULL REFERENCES commit_gate(gate_id)
                    DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER require_commit_gate AFTER INSERT ON first_receipts
            BEGIN
                INSERT INTO commit_gate_checks VALUES (NEW.receipt_id, 1);
            END;
        ''')

    def clear_deferred_commit_failure(self):
        self.isolated.execute('DROP TRIGGER require_commit_gate')
