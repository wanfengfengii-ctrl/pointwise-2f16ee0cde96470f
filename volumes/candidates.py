from archive_core import InputError
from specimens.identity import specimen_key


def bind_candidates(draft, registrations):
    declared = {specimen_key(key) for key in draft.specimen_ids}
    missing = sorted(key for key in declared if registrations.get(key) is None)
    outside = sorted(
        (point, key) for point, choices in draft.candidates.items()
        for key in choices if key not in declared
    )
    if missing or outside:
        details = []
        if missing:
            details.append(f'unregistered originals {missing!r}')
        if outside:
            details.append(f'candidate references outside volume {outside!r}')
        raise InputError(' | '.join(details))
    return {point: tuple(choices) for point, choices in draft.candidates.items()}
