from collections import deque


def _augment(candidates, root, occupied, owners, assignments):
    pending = deque([root])
    seen_points = {root}
    predecessor = {}
    free = None
    while pending and free is None:
        point = pending.popleft()
        for specimen in candidates[point]:
            if specimen in occupied or specimen in predecessor:
                continue
            predecessor[specimen] = point
            owner = owners.get(specimen)
            if owner is None:
                free = specimen
                break
            if owner not in seen_points:
                seen_points.add(owner)
                pending.append(owner)
    if free is None:
        return False

    # Walk backward along the alternating path and move each owner onto its new specimen.
    while free is not None:
        point = predecessor[free]
        owners[free] = point
        previous = assignments.get(point)
        assignments[point] = free
        free = previous
    return True


def can_complete_assignment(candidates, fixed=None):
    """Return whether every point can be assigned, respecting any fixed point-to-specimen edges."""
    fixed = {} if fixed is None else fixed
    occupied = set(fixed.values())
    if len(occupied) != len(fixed):
        return False
    if any(point not in candidates or specimen not in candidates[point]
           for point, specimen in fixed.items()):
        return False

    owners = {}
    assignments = {}
    for point in candidates:
        if point not in fixed and not _augment(candidates, point, occupied, owners, assignments):
            return False
    return True
