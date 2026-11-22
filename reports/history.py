from archive_core import MissingRecord, text_key
from reports.receipts import load_first_receipt
from reports.reconcile import verify_original_bundle
from reports.store import load_report_row


def read_report(connection, report_id):
    report_id = text_key(report_id, 'report ID')
    report = load_report_row(connection, report_id)
    if report is None:
        raise MissingRecord(f'unknown report {report_id!r}')
    return verify_original_bundle(report, load_first_receipt(connection, report_id))
