from dataclasses import dataclass

from archive_core import ArchiveError, ReconciliationError
from reports.receipts import FirstReceipt, make_first_receipt
from reports.store import ReportRecord


@dataclass(frozen=True)
class ReportBundle:
    report: ReportRecord
    first_receipt: FirstReceipt


def verify_original_bundle(report, first_receipt):
    try:
        expected_report = ReportRecord.from_request(report.request, report.total_um)
    except ArchiveError as exc:
        raise ReconciliationError(f'invalid original report {report.report_id!r}') from exc
    if expected_report != report:
        raise ReconciliationError(f'body and request disagree for report {report.report_id!r}')

    request = report.request
    expected_receipt = make_first_receipt(report.report_id, request.request_id, request.intake_id,
                                          request.packet_id, report.body)
    if first_receipt != expected_receipt:
        raise ReconciliationError(f'missing or contradictory first receipt for {report.report_id!r}')
    return ReportBundle(report, first_receipt)
