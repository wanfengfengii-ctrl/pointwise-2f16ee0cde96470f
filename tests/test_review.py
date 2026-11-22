import json

from archive_core import RequestError
from reports.history import read_report
from review.adjudicate import review
from review.results import ReviewOutcome
from review.workbench import review_and_sign
from tests.fixtures import ArchiveCase, LEGACY_PACKET_ID, LEGACY_VOLUME_ID, SHARED_READINGS, shared_candidates


class ReviewTests(ArchiveCase):
    def test_single_review_after_source_closed(self):
        received = self.delivered((('foil-7', 7, 'SLIP-07'),), {'A': ['foil-7']}, ['A'])
        self.source.close()
        decision, bundle = review_and_sign(self.isolated, received.intake_id, ['A'])
        self.assertEqual(decision.outcome, ReviewOutcome.SIGNABLE)
        self.assertEqual(decision.total_um, 7)
        self.assertEqual(bundle.report.total_um, 7)
        self.assertEqual(bundle.report.request.packet_id, received.envelope.packet_id)
        self.assertEqual(bundle.first_receipt.report_id, bundle.report.report_id)
        self.assertEqual(read_report(self.isolated, bundle.report.report_id), bundle)
        self.assertEqual(self.signing_count(), (1, 1))

    def test_selection_rejection(self):
        received = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        self.source.close()
        invalid = (('in-unknown', ['A']), (received.intake_id, []), (received.intake_id, ['C']),
                   (received.intake_id, ['A', 'A']), (received.intake_id, ['A', 'B', 'C']),
                   (received.intake_id, 'A'))
        for intake_id, points in invalid:
            with self.subTest(intake=intake_id, points=points), self.assertRaises(RequestError):
                review_and_sign(self.isolated, intake_id, points)
        self.assertEqual(self.signing_count(), (0, 0))

    def test_receipt_scope_for_same_point_name(self):
        first = self.delivered((('foil-7', 7, 'SLIP-07'),), {'A': ['foil-7']}, ['A'])
        second = self.delivered((('foil-11', 11, 'SLIP-11'),), {'A': ['foil-11']}, ['A'])
        self.source.close()
        for received, expected in ((first, 7), (second, 11)):
            with self.subTest(intake=received.intake_id):
                decision, bundle = review_and_sign(self.isolated, received.intake_id, ['A'])
                self.assertEqual(decision.total_um, expected)
                self.assertEqual(bundle.report.total_um, expected)
                self.assertEqual(bundle.report.request.intake_id, received.intake_id)
                self.assertEqual(bundle.report.request.packet_id, received.envelope.packet_id)
                self.assertEqual(bundle.first_receipt.packet_id, received.envelope.packet_id)
        self.assertEqual(self.signing_count(), (2, 2))

    def test_legacy_review_and_historical_pickup(self):
        legacy = self.accept_legacy()
        self.source.close()
        decision, bundle = review_and_sign(self.isolated, legacy.intake_id, ['A'])
        self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.SIGNABLE, 7))
        self.assertEqual(bundle.report.request.volume_id, LEGACY_VOLUME_ID)
        self.assertEqual(bundle.first_receipt.packet_id, LEGACY_PACKET_ID)
        self.reopen_isolated()
        self.assertEqual(read_report(self.isolated, bundle.report.report_id), bundle)

    def test_joint_review_after_source_closed(self):
        candidates = shared_candidates('r13')
        received = self.delivered(SHARED_READINGS, candidates, ['A', 'B'])
        self.source.close()
        singles = []
        for point in ('A', 'B'):
            single, bundle = review_and_sign(self.isolated, received.intake_id, [point])
            self.assertEqual(single.outcome, ReviewOutcome.AMBIGUOUS)
            self.assertIsNone(single.total_um)
            self.assertIsNone(bundle)
            singles.append(single.outcome.value)
        self.assertEqual(self.signing_count(), (0, 0))

        pair, bundle = review_and_sign(self.isolated, received.intake_id, ['A', 'B'])
        self.assertEqual((pair.outcome, pair.total_um), (ReviewOutcome.SIGNABLE, 18), 'V6_JOINT_ASSIGNMENT_18')
        self.assertIsNotNone(bundle)
        original = read_report(self.isolated, bundle.report.report_id)
        self.assertEqual(original, bundle)
        self.assertEqual(original.report.total_um, 18)
        self.assertEqual(original.report.request.points, ('A', 'B'))
        self.assertEqual(original.first_receipt.request_id, pair.request.request_id)
        self.assertEqual(self.signing_count(), (1, 1))
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'V6',
            'input': {'specimens': SHARED_READINGS, 'candidates': candidates, 'disclosed': ['A', 'B']},
            'expected': {'single': ['ambiguous', 'ambiguous'], 'pair': 'signable', 'total_um': 18},
            'actual': {'single': singles, 'pair': pair.outcome.value, 'total_um': pair.total_um},
            'downstream_expected': {'report_total_um': 18, 'report_count': 1, 'first_receipt_count': 1},
            'downstream_actual': {'report_total_um': original.report.total_um,
                                  'report_count': self.signing_count()[0],
                                  'first_receipt_count': self.signing_count()[1]},
            'code_paths': ['packets/evidence.py', 'packets/receive.py', 'review/adjudicate.py',
                           'review/feasibility.py', 'reports/sign.py', 'reports/history.py'],
            'oracle': 'C holds r13. The only pairs are r07/r11 and r11/r07, each totaling 18 um.',
        }, sort_keys=True))

    def test_alternate_hidden_occupancy(self):
        first = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        alternate = self.delivered(SHARED_READINGS, shared_candidates('r07'), ['A', 'B'])
        self.source.close()
        for received, expected, marker in ((alternate, 24, 'V6_JOINT_ASSIGNMENT_24'),
                                            (first, 18, 'V6_JOINT_ASSIGNMENT_18')):
            with self.subTest(intake=received.intake_id):
                decision, bundle = review_and_sign(self.isolated, received.intake_id, ['B', 'A'])
                self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.SIGNABLE, expected), marker)
                self.assertEqual(bundle.report.total_um, expected)
                self.assertEqual(bundle.report.request.volume_id, received.envelope.volume_id)
        self.assertEqual(self.signing_count(), (2, 2))

    def test_selection_order_replays_same_first_receipt(self):
        received = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B'])
        self.source.close()
        forward = review_and_sign(self.isolated, received.intake_id, ['A', 'B'])
        reverse = review_and_sign(self.isolated, received.intake_id, ['B', 'A'])
        self.assertEqual(forward, reverse)
        decision, bundle = reverse
        self.assertEqual(decision.request.points, ('A', 'B'))
        self.assertEqual(bundle.report.total_um, 18)
        self.assertEqual(self.signing_count(), (1, 1))

    def test_equal_reading_specimens_can_both_be_assigned(self):
        received = self.delivered((('left', 7, 'SLIP-L'), ('right', 7, 'SLIP-R')),
                                  {'A': ('left', 'right'), 'B': ('left', 'right')}, ['A', 'B'])
        self.source.close()
        decision, bundle = review_and_sign(self.isolated, received.intake_id, ['A', 'B'])
        self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.SIGNABLE, 14))
        self.assertEqual(bundle.report.total_um, 14)

    def test_true_pair_ambiguity(self):
        received = self.delivered(SHARED_READINGS, shared_candidates(), ['A', 'B'])
        self.source.close()
        decision, bundle = review_and_sign(self.isolated, received.intake_id, ['A', 'B'])
        self.assertEqual(decision.outcome, ReviewOutcome.AMBIGUOUS)
        self.assertIsNone(decision.total_um)
        self.assertIsNone(bundle)
        self.assertEqual(self.signing_count(), (0, 0))

    def test_exact_integer_sum_across_sqlite_boundary(self):
        first = self.delivered((('large', 9223372036854775807, 'SLIP-L'), ('seven', 7, 'SLIP-7')),
                               {'A': ['large'], 'B': ['seven']}, ['A', 'B'])
        huge = 10 ** 4350 + 5
        second = self.delivered((('huge', huge, 'SLIP-H'), ('seven', 7, 'SLIP-7')),
                                {'A': ['huge'], 'B': ['seven']}, ['A', 'B'])
        self.source.close()
        signed = []
        for received, expected in ((first, 9223372036854775814), (second, huge + 7)):
            decision, bundle = review_and_sign(self.isolated, received.intake_id, ['A', 'B'])
            self.assertEqual(decision.outcome, ReviewOutcome.SIGNABLE)
            self.assertEqual(decision.total_um, expected)
            signed.append((bundle, expected))
        self.reopen_isolated()
        for bundle, expected in signed:
            self.assertEqual(read_report(self.isolated, bundle.report.report_id).report.total_um, expected)

    def test_conflicting_use_is_no_assignment(self):
        taken = self.delivered((('only', 7, 'SLIP-07'),), {'A': ['only'], 'B': ['only']}, ['A', 'B'])
        self.source.close()
        self.assert_no_assignment(taken.intake_id, ['A', 'B'])

    def test_unselected_disconnected_conflict(self):
        received = self.delivered((('r07', 7, 'SLIP-07'), ('r11', 11, 'SLIP-11')),
                                  {'A': ['r07'], 'B': ['r11'], 'C': ['r11']}, ['A', 'B', 'C'])
        self.source.close()
        self.assert_no_assignment(received.intake_id, ['A'])

    def test_hidden_empty_candidate_remains_an_obligation(self):
        received = self.delivered((('r07', 7, 'SLIP-07'),), {'A': ['r07'], 'C': []}, ['A'])
        self.source.close()
        self.assert_no_assignment(received.intake_id, ['A'])

    def assert_no_assignment(self, intake_id, points):
        decision, bundle = review_and_sign(self.isolated, intake_id, points)
        self.assertEqual(decision.outcome, ReviewOutcome.NO_ASSIGNMENT)
        self.assertIsNone(decision.total_um)
        self.assertIsNone(bundle)
        self.assertEqual(self.signing_count(), (0, 0))
