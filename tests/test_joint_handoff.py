from review.results import ReviewOutcome
from review.workbench import review_and_sign
from tests.fixtures import ArchiveCase, SHARED_READINGS, shared_candidates


class JointHandoffTests(ArchiveCase):
    def test_joint_qualification_with_all_points_disclosed(self):
        packet = self.delivered(SHARED_READINGS, shared_candidates('r13'), ['A', 'B', 'C'])
        self.source.close()
        for point in ('A', 'B'):
            decision, bundle = review_and_sign(self.isolated, packet.intake_id, [point])
            self.assertEqual(decision.outcome, ReviewOutcome.AMBIGUOUS)
            self.assertIsNone(bundle)
        decision, bundle = review_and_sign(self.isolated, packet.intake_id, ['A', 'B'])
        self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.SIGNABLE, 18),
                         'V6_FULL_DISCLOSURE_JOINT_18')
        self.assertEqual(bundle.report.total_um, 18)
        self.assertEqual(self.signing_count(), (1, 1))

    def test_same_single_point_choices_different_pair_qualification(self):
        readings = (*SHARED_READINGS, ('r17', 17, 'SLIP-17'))
        visible = {'A': ['r07', 'r11'], 'B': ['r13', 'r17']}
        unique = self.delivered(readings, {**visible, 'C': ['r07', 'r13'], 'D': ['r11', 'r17']},
                                ['A', 'B'])
        ambiguous = self.delivered(readings, {**visible, 'C': ['r07', 'r17'], 'D': ['r11', 'r13']},
                                   ['A', 'B'])
        self.source.close()
        for packet in (unique, ambiguous):
            for point in ('A', 'B'):
                decision, bundle = review_and_sign(self.isolated, packet.intake_id, [point])
                self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.AMBIGUOUS, None))
                self.assertIsNone(bundle)
        decision, bundle = review_and_sign(self.isolated, ambiguous.intake_id, ['A', 'B'])
        self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.AMBIGUOUS, None))
        self.assertIsNone(bundle)
        self.assertEqual(self.signing_count(), (0, 0))
        decision, bundle = review_and_sign(self.isolated, unique.intake_id, ['A', 'B'])
        self.assertEqual((decision.outcome, decision.total_um), (ReviewOutcome.SIGNABLE, 24),
                         'V6_EQUAL_MARGINALS_JOINT_24')
        self.assertEqual(bundle.report.total_um, 24)
        self.assertEqual(self.signing_count(), (1, 1))
