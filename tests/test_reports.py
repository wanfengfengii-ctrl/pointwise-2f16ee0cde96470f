import json
import sqlite3
from dataclasses import replace

from archive_core import MissingRecord, ReconciliationError, SignError
from packets.receive import read_received
from reports.history import read_report
from reports.sign import sign
from reports.store import initialize_isolated
from review.adjudicate import review
from review.results import ReviewOutcome, make_decision
from review.workbench import review_and_sign
from tests.fixtures import ArchiveCase, SHARED_READINGS, shared_candidates, table_count


class ReportTests(ArchiveCase):
    def test_commit_failure_rolls_back_report_and_receipt_then_retries(self):
        first = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        next_packet = self.delivered(SHARED_READINGS, shared_candidates('r07'), ['A', 'B'])
        self.source.close()
        _, original = review_and_sign(self.isolated, first.intake_id, ['A', 'B'])
        self.assertEqual(original.report.total_um, 18)
        self.install_deferred_commit_failure()
        with self.assertRaises(SignError) as failure:
            review_and_sign(self.isolated, next_packet.intake_id, ['A', 'B'])
        self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
        self.assertIn('FOREIGN KEY', str(failure.exception.__cause__))
        self.assertFalse(self.isolated.in_transaction)
        independent = self.connect(self.isolated_path)
        self.assertEqual(self.signing_count(independent), (1, 1))
        self.assertEqual(independent.execute('SELECT count(*) FROM commit_gate_checks').fetchone()[0], 0)
        self.assertEqual(read_report(independent, original.report.report_id), original)

        self.clear_deferred_commit_failure()
        decision, new_bundle = review_and_sign(self.isolated, next_packet.intake_id, ['B', 'A'])
        self.assertEqual(decision.total_um, 24)
        self.assertEqual(new_bundle.report.total_um, 24)
        self.assertNotEqual(new_bundle.first_receipt.receipt_id, original.first_receipt.receipt_id)
        self.assertEqual(sign(self.isolated, decision), new_bundle)
        self.assertEqual(read_report(independent, new_bundle.report.report_id), new_bundle)
        self.assertEqual(self.signing_count(independent), (2, 2))

    def test_sign_rejects_ineligible_or_inconsistent_decisions(self):
        unqualified = self.delivered(SHARED_READINGS, shared_candidates(), ['A', 'B'])
        qualified = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        self.source.close()
        ambiguous = review(self.isolated, unqualified.intake_id, ['A', 'B'])
        eligible = review(self.isolated, qualified.intake_id, ['A', 'B'])
        self.assertEqual(ambiguous.outcome, ReviewOutcome.AMBIGUOUS)
        invalid = (
            ambiguous,
            make_decision(ambiguous.request, ReviewOutcome.SIGNABLE, 18),
            replace(eligible, request=replace(eligible.request, packet_id=unqualified.envelope.packet_id)),
            replace(eligible, total_um=24),
        )
        for decision in invalid:
            with self.subTest(decision=decision), self.assertRaises(SignError):
                sign(self.isolated, decision)
        self.assertEqual(self.signing_count(), (0, 0))
        original = sign(self.isolated, eligible)
        with self.assertRaises(SignError):
            sign(self.isolated, replace(eligible, total_um=20))
        self.assertEqual(read_report(self.isolated, original.report.report_id), original)
        self.assertEqual(self.signing_count(), (1, 1))

    def test_later_local_signing_and_original_pickup(self):
        first = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        self.source.close()
        _, original = review_and_sign(self.isolated, first.intake_id, ['A', 'B'])
        self.assertEqual(original.report.total_um, 18)
        self.source = self.connect(self.source_path)
        updated = self.delivered(SHARED_READINGS, shared_candidates('r07'), ['A', 'B'])
        self.source.close()
        _, later = review_and_sign(self.isolated, updated.intake_id, ['A', 'B'])
        self.assertEqual(later.report.total_um, 24)
        self.reopen_isolated()
        self.assertEqual(self.signing_count(), (2, 2))
        for original_bundle, received, expected_decimal in ((original, first, '18'), (later, updated, '24')):
            with self.subTest(report=original_bundle.report.report_id):
                fetched = read_report(self.isolated, original_bundle.report.report_id)
                self.assertEqual(fetched, original_bundle)
                copied = json.loads(fetched.report.body)
                self.assertEqual(copied['total_um'], expected_decimal)
                self.assertEqual(copied['points'], ['A', 'B'])
                self.assertEqual(copied['packet_id'], received.envelope.packet_id)
                self.assertEqual(copied['request_id'], fetched.first_receipt.request_id)
                self.assertEqual(fetched.first_receipt.intake_id, received.intake_id)
                self.assertEqual(read_received(self.isolated, received.intake_id), received)

    def test_isolated_reinitialize_preserves_non_sample_work(self):
        received = self.delivered((('workpiece-62', 62, 'LOCAL-BOOK-62'),),
                                  {'Station North': ['workpiece-62']}, ['Station North'])
        self.source.close()
        _, bundle = review_and_sign(self.isolated, received.intake_id, ['Station North'])
        initialize_isolated(self.isolated)
        self.reopen_isolated()
        self.assertEqual(read_received(self.isolated, received.intake_id), received)
        self.assertEqual(read_report(self.isolated, bundle.report.report_id), bundle)
        self.assertEqual(bundle.report.total_um, 62)
        self.assertEqual(table_count(self.isolated, 'received_packets'), 1)
        self.assertEqual(self.signing_count(), (1, 1))

    def test_unknown_number(self):
        with self.assertRaises(MissingRecord):
            read_report(self.isolated, 'report-unknown')
        self.assertEqual(self.signing_count(), (0, 0))

    def test_contradictory_stored_receipt_stops_delivery(self):
        packet = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        self.source.close()
        _, bundle = review_and_sign(self.isolated, packet.intake_id, ['A', 'B'])
        self.isolated.execute('UPDATE first_receipts SET body_sha256 = ? WHERE report_id = ?',
                              ('disagrees', bundle.report.report_id))
        self.isolated.commit()
        with self.assertRaises(ReconciliationError):
            read_report(self.isolated, bundle.report.report_id)
        self.assertEqual(self.signing_count(), (1, 1))
        self.assertEqual(self.isolated.execute('SELECT body_sha256 FROM first_receipts').fetchone()[0],
                         'disagrees')
