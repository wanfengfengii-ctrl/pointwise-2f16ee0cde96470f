from itertools import product

from archive_core import InputError, MissingRecord, PacketError, RequestError
from packets.receive import read_received
from review.feasibility import can_complete_assignment
from review.requests import make_request
from review.results import ReviewOutcome, make_decision


def _feasible_readings(evidence, token):
    readings = set()
    graph = evidence.candidates
    for specimen in graph[token]:
        if can_complete_assignment(graph, {token: specimen}):
            readings.add(evidence.originals[specimen].micrometers)
    return readings


def review(connection, intake_id, points):
    try:
        received = read_received(connection, intake_id)
    except (InputError, MissingRecord) as exc:
        raise RequestError(f'cannot select from intake {intake_id!r}') from exc
    request = make_request(received, points)
    evidence = received.evidence
    if not can_complete_assignment(evidence.candidates):
        return make_decision(request, ReviewOutcome.NO_ASSIGNMENT)

    selected = tuple(evidence.visible[point] for point in request.points)
    readings = [_feasible_readings(evidence, token) for token in selected]
    total = None
    for values in product(*readings):
        candidate_total = sum(values)
        if total is not None and total != candidate_total:
            return make_decision(request, ReviewOutcome.AMBIGUOUS)
        total = candidate_total
    if total is None:
        raise PacketError('no selectable combination in a feasible packet')
    return make_decision(request, ReviewOutcome.SIGNABLE, total)
