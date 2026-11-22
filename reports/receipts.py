from dataclasses import dataclass

from archive_core import canonical, content_id, sha256_hex


@dataclass(frozen=True)
class FirstReceipt:
    receipt_id: str
    report_id: str
    request_id: str
    intake_id: str
    packet_id: str
    body_sha256: str


def initialize_first_receipts(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS first_receipts (
            receipt_id TEXT PRIMARY KEY NOT NULL,
            report_id TEXT UNIQUE NOT NULL REFERENCES reports(report_id),
            request_id TEXT NOT NULL,
            intake_id TEXT NOT NULL,
            packet_id TEXT NOT NULL,
            body_sha256 TEXT NOT NULL
        )
    ''')


def make_first_receipt(report_id, request_id, intake_id, packet_id, body):
    checksum = sha256_hex(body)
    binding = [report_id, request_id, intake_id, packet_id, checksum]
    return FirstReceipt(content_id('first', canonical(binding)), *binding)


def insert_first_receipt(connection, receipt):
    connection.execute('''
        INSERT INTO first_receipts
            (receipt_id, report_id, request_id, intake_id, packet_id, body_sha256)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (receipt.receipt_id, receipt.report_id, receipt.request_id, receipt.intake_id,
          receipt.packet_id, receipt.body_sha256))


def load_first_receipt(connection, report_id):
    row = connection.execute('''
        SELECT receipt_id, report_id, request_id, intake_id, packet_id, body_sha256
        FROM first_receipts WHERE report_id = ?
    ''', (report_id,)).fetchone()
    return FirstReceipt(*row) if row is not None else None
