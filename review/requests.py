from dataclasses import dataclass

from archive_core import InputError, RequestError, canonical, content_id, name_sequence, text_key
from packets.receive import ReceivedPacket


@dataclass(frozen=True)
class ReviewRequest:
    request_id: str
    intake_id: str
    packet_id: str
    volume_id: str
    points: tuple[str, ...]

    def binding(self):
        return {'intake_id': self.intake_id, 'packet_id': self.packet_id,
                'volume_id': self.volume_id, 'points': list(self.points)}

    def validate(self):
        text_key(self.intake_id, 'intake ID')
        text_key(self.packet_id, 'packet ID')
        text_key(self.volume_id, 'volume ID')
        if _selected_points(self.points) != self.points:
            raise RequestError('request points are not in canonical order')
        if self.request_id != content_id('req', canonical(self.binding())):
            raise RequestError('request ID does not match its binding')


def _selected_points(points):
    try:
        points = name_sequence(points, 'selected point')
    except InputError as exc:
        raise RequestError(str(exc)) from exc
    if len(points) not in (1, 2) or len(set(points)) != len(points):
        raise RequestError('review requires one or two distinct disclosed points')
    return tuple(sorted(points))


def make_request(received: ReceivedPacket, points):
    points = _selected_points(points)
    missing = sorted(set(points).difference(received.envelope.manifest.points))
    if missing:
        raise RequestError(f'points not disclosed by specified packet {missing!r}')
    binding = {'intake_id': received.intake_id, 'packet_id': received.envelope.packet_id,
               'volume_id': received.envelope.volume_id, 'points': list(points)}
    return ReviewRequest(content_id('req', canonical(binding)), received.intake_id,
                         received.envelope.packet_id, received.envelope.volume_id, points)
