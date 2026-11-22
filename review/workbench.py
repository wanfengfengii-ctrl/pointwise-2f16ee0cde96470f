from reports.sign import sign
from review.adjudicate import review
from review.results import ReviewOutcome


def review_and_sign(connection, intake_id, points):
    decision = review(connection, intake_id, points)
    if decision.outcome is ReviewOutcome.SIGNABLE:
        return decision, sign(connection, decision)
    return decision, None
