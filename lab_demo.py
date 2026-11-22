import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from packets.issue import issue
from packets.receive import receive
from reports.history import read_report
from reports.store import initialize_isolated
from review.workbench import review_and_sign
from specimens.register import register
from volumes.draft import create_draft
from volumes.freeze import freeze
from volumes.store import initialize_source


_SAMPLE = Path(__file__).resolve().parent / 'samples' / 'night_shift.json'


def _issue_shift(source_path, isolated, sample):
    with closing(sqlite3.connect(source_path)) as source:
        initialize_source(source)
        for row in sample['specimens']:
            register(source, row['specimen_id'], row['micrometers'], row['source_reference'])
        intake_ids = []
        for candidates in sample['volumes']:
            draft = create_draft((row['specimen_id'] for row in sample['specimens']), candidates)
            frozen = freeze(source, draft)
            envelope = issue(source, frozen.volume_id, sample['disclosed'])
            intake_ids.append(receive(isolated, envelope.packet_id, envelope.wire).intake_id)
    return intake_ids


def main():
    sample = json.loads(_SAMPLE.read_bytes())
    with TemporaryDirectory(prefix='specimen-shift-') as temp:
        directory = Path(temp)
        isolated_path = directory / 'night.sqlite'
        with closing(sqlite3.connect(isolated_path)) as isolated:
            initialize_isolated(isolated)
            first, revised = _issue_shift(directory / 'source.sqlite', isolated, sample)
            single_outcomes = []
            for point in sample['disclosed']:
                decision, receipt = review_and_sign(isolated, first, (point,))
                single_outcomes.append(decision.outcome.value)
                if receipt is not None:
                    raise AssertionError('sample singles must not produce first receipts')
            totals = []
            signed = []
            for intake_id in (first, revised):
                decision, bundle = review_and_sign(isolated, intake_id, sample['disclosed'])
                if bundle is None:
                    raise AssertionError(f'sample joint review failed: {decision.outcome.value}')
                totals.append(bundle.report.total_um)
                signed.append(bundle)

        with closing(sqlite3.connect(isolated_path)) as isolated:
            initialize_isolated(isolated)
            original = read_report(isolated, signed[0].report.report_id)
            correction = read_report(isolated, signed[1].report.report_id)
            if (original, correction) != tuple(signed):
                raise AssertionError('reopened archive did not return the original reports and receipts')

        expected = {'single_outcomes': ['ambiguous', 'ambiguous'], 'signed_totals_um': [18, 24]}
        actual = {'single_outcomes': single_outcomes, 'signed_totals_um': totals}
        downstream = {'original_um': original.report.total_um, 'later_um': correction.report.total_um,
                      'original_first_receipt_preserved': original.first_receipt == signed[0].first_receipt}
        expected_downstream = {'original_um': 18, 'later_um': 24, 'original_first_receipt_preserved': True}
        if actual != expected or downstream != expected_downstream:
            raise AssertionError(f'wrong sample results: {actual!r} / {downstream!r}')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'V9.later_local_signing', 'input': sample, 'expected': expected,
            'actual': actual, 'downstream_expected': expected_downstream, 'downstream_actual': downstream,
            'code_paths': ['volumes/freeze.py', 'packets/issue.py', 'packets/receive.py',
                           'review/adjudicate.py', 'reports/sign.py', 'reports/history.py'],
            'oracle': 'C uses r13 in the first volume and r07 in the later volume. '
                      'A and B must split the remaining two specimens, so the sums are 7+11 and 11+13.',
        }, sort_keys=True))


if __name__ == '__main__':
    main()
