from dataclasses import dataclass

from archive_core import InputError, ReconciliationError, canonical, content_id, name_sequence, read_document
from packets.receive import initialize_intake
from reports.receipts import initialize_first_receipts
from review.requests import ReviewRequest
from specimens.measurements import decode_micrometers, encode_micrometers


@dataclass(frozen=True)
class ReportRecord:
    report_id: str
    request: ReviewRequest
    body: bytes

    @classmethod
    def from_request(cls, request, total_um):
        request.validate()
        body = canonical({**request.binding(), 'request_id': request.request_id,
                          'total_um': encode_micrometers(total_um), 'unit': 'um'})
        return cls(content_id('report', body), request, body)

    @property
    def total_um(self):
        payload = read_document(self.body)
        if type(payload) is not dict or 'total_um' not in payload:
            raise InputError('report body has no total')
        return decode_micrometers(payload['total_um'])


def initialize_isolated(connection):
    initialize_intake(connection)
    connection.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY NOT NULL,
            request_id TEXT UNIQUE NOT NULL,
            intake_id TEXT NOT NULL REFERENCES received_packets(intake_id),
            packet_id TEXT NOT NULL,
            volume_id TEXT NOT NULL,
            points BLOB NOT NULL,
            body BLOB NOT NULL
        )
    ''')
    initialize_first_receipts(connection)


def insert_report(connection, report):
    request = report.request
    connection.execute('''
        INSERT INTO reports (report_id, request_id, intake_id, packet_id, volume_id, points, body)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (report.report_id, request.request_id, request.intake_id, request.packet_id,
          request.volume_id, canonical(list(request.points)), report.body))


def _read_row(row):
    if row is None:
        return None
    report_id, request_id, intake_id, packet_id, volume_id, points, body = row
    try:
        selected = read_document(points)
        if type(selected) is not list:
            raise InputError('report points must be an array')
        request = ReviewRequest(request_id, intake_id, packet_id, volume_id,
                                name_sequence(selected, 'report point'))
    except InputError as exc:
        raise ReconciliationError(f'invalid stored request for report {report_id!r}') from exc
    return ReportRecord(report_id, request, body)


def load_report_row(connection, report_id):
    return _read_row(connection.execute('''
        SELECT report_id, request_id, intake_id, packet_id, volume_id, points, body
        FROM reports WHERE report_id = ?
    ''', (report_id,)).fetchone())


def load_report_by_request(connection, request_id):
    return _read_row(connection.execute('''
        SELECT report_id, request_id, intake_id, packet_id, volume_id, points, body
        FROM reports WHERE request_id = ?
    ''', (request_id,)).fetchone())
