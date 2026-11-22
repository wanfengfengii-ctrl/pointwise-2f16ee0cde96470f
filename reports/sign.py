import sqlite3

from archive_core import PacketError, RequestError, SignError, write_transaction
from reports.history import read_report
from reports.receipts import insert_first_receipt, make_first_receipt
from reports.store import ReportRecord, insert_report, load_report_by_request
from review.adjudicate import review
from review.results import require_signable


def sign(connection, decision):
    total_um = require_signable(decision)
    request = decision.request
    try:
        with write_transaction(connection):
            actual = review(connection, request.intake_id, request.points)
            if actual != decision:
                raise SignError('decision does not match the specified packet and selection')
            draft = ReportRecord.from_request(request, total_um)
            previous = load_report_by_request(connection, request.request_id)
            if previous is None:
                insert_report(connection, draft)
                receipt = make_first_receipt(draft.report_id, request.request_id, request.intake_id,
                                             request.packet_id, draft.body)
                insert_first_receipt(connection, receipt)
            elif previous != draft:
                raise SignError('signed request disagrees with the original report')
            bundle = read_report(connection, draft.report_id)
    except (sqlite3.Error, PacketError, RequestError) as exc:
        raise SignError(f'could not commit signing for {request.request_id!r}') from exc
    return bundle
