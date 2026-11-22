from dataclasses import dataclass

from archive_core import InputError, name_sequence


@dataclass(frozen=True)
class DisclosureManifest:
    points: tuple[str, ...]


def build_manifest(available_points, disclosed_points):
    points = name_sequence(disclosed_points, 'disclosed point')
    if not points or len(set(points)) != len(points):
        raise InputError('disclosure requires a nonempty list of distinct points')
    unknown = sorted(set(points).difference(available_points))
    if unknown:
        raise InputError(f'points missing from frozen volume {unknown!r}')
    return DisclosureManifest(tuple(sorted(points)))


def read_manifest(raw):
    if type(raw) is not list:
        raise InputError('packet disclosure list must be a JSON array')
    points = name_sequence(raw, 'disclosed point')
    if not points or points != tuple(sorted(set(points))):
        raise InputError('invalid canonical disclosure list')
    return DisclosureManifest(points)
