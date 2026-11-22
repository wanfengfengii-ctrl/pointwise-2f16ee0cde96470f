from itertools import product

from archive_core import InputError, MissingRecord, PacketError, RequestError
from packets.receive import read_received
from review.feasibility import can_complete_assignment
from review.requests import make_request
from review.results import ReviewOutcome, make_decision


def _feasible_totals(evidence, selected):
    graph = evidence.candidates
    totals = set()
    for combo in product(*(graph[token] for token in selected)):
        if len(set(combo)) != len(combo) and len(combo) > 1:
            continue
        if can_complete_assignment(graph, dict(zip(selected, combo))):
            totals.add(sum(evidence.originals[specimen].micrometers for specimen in combo))
            if len(totals) > 1:
                break
    return totals


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
    totals = _feasible_totals(evidence, selected)
    if not totals:
        raise PacketError('no selectable combination in a feasible packet')
    if len(totals) != 1:
        return make_decision(request, ReviewOutcome.AMBIGUOUS)
    return make_decision(request, ReviewOutcome.SIGNABLE, totals.pop())
