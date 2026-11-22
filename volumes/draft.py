from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from archive_core import InputError, name_sequence, text_key


@dataclass(frozen=True)
class VolumeDraft:
    specimen_ids: tuple[str, ...]
    candidates: Mapping[str, tuple[str, ...]]


def create_draft(specimen_ids, candidates):
    if not isinstance(candidates, Mapping) or not candidates:
        raise InputError('a volume requires an explicit candidate table with at least one point')
    specimen_ids = tuple(sorted(set(name_sequence(specimen_ids, 'specimen ID'))))
    edges = {}
    for point, choices in candidates.items():
        point = text_key(point, 'point name')
        edges[point] = tuple(sorted(set(name_sequence(choices, f'candidates for {point!r}'))))
    return VolumeDraft(specimen_ids, MappingProxyType(dict(sorted(edges.items()))))
