from dataclasses import dataclass
from enum import Enum

from archive_core import InputError, SignError
from review.requests import ReviewRequest
from specimens.measurements import require_micrometers


class ReviewOutcome(str, Enum):
    NO_ASSIGNMENT = 'no_assignment'
    AMBIGUOUS = 'ambiguous'
    SIGNABLE = 'signable'


@dataclass(frozen=True)
class ReviewDecision:
    request: ReviewRequest
    outcome: ReviewOutcome
    total_um: int | None


def make_decision(request, outcome, total_um=None):
    if not isinstance(outcome, ReviewOutcome):
        raise InputError('invalid review outcome')
    if outcome is ReviewOutcome.SIGNABLE:
        require_micrometers(total_um)
    elif total_um is not None:
        raise InputError('unsigned outcomes cannot carry a signable total')
    return ReviewDecision(request, outcome, total_um)


def require_signable(decision):
    if not isinstance(decision, ReviewDecision) or decision.outcome is not ReviewOutcome.SIGNABLE:
        raise SignError('review decision is not signable')
    try:
        if not isinstance(decision.request, ReviewRequest):
            raise InputError('missing review request')
        decision.request.validate()
        return require_micrometers(decision.total_um)
    except InputError as exc:
        raise SignError('invalid review decision binding or total') from exc
    except ValueError as exc:
        raise SignError('invalid review request') from exc
