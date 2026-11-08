#!/usr/bin/env python3
"""Verify preserved ZIP members and sample identities; no scientific calculations."""
from pathlib import Path
import csv
import hashlib
import io
import json
import zipfile


def read_csv(stream):
    return list(csv.DictReader(stream))


def verify_saved_outputs(root):
    with (root/'metadata/SUPPLEMENTARY_OUTPUT_INDEX.csv').open(encoding='utf-8', newline='') as f:
        index = read_csv(f)
    can = {}
    for f in sorted((root/'data/manifests').glob('*.part-*.csv')):
        with f.open(encoding='utf-8-sig', newline='') as h:
            for row in read_csv(h):
                can[row['sample_id']] = row
    expected = {d['member']: d for d in index}
    assert len(expected) == len(index)
    coverage = json.loads((root/'metadata/SAVED_OUTPUT_COVERAGE.json').read_text())
    checks = {d['member']: d for d in coverage['package_identity_checks'] if d.get('population') in ('test', 'validation')}
    archive = root/'data/supplementary/saved_outputs_v1.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == coverage['archive_sha256']
    assert archive.stat().st_size == coverage['archive_bytes']
    with zipfile.ZipFile(archive) as z:
        members = z.namelist()
        assert len(members) == len(set(members)) and set(members) == set(expected)
        assert len(members) == coverage['members']
        for member in members:
            assert not Path(member).is_absolute() and '..' not in Path(member).parts
            data = z.read(member)
            assert len(data) == int(expected[member]['bytes']), member
            assert hashlib.sha256(data).hexdigest() == expected[member]['sha256'], member
            if member in checks:
                check = checks[member]
                records = read_csv(io.StringIO(data.decode('utf-8-sig')))
                idcol = 'sample_id' if 'sample_id' in records[0] else 'graph_id'
                wanted = {s for s,v in can.items() if v['split'] == ('val' if check['population']=='validation' else 'test')}
                assert len(records) == len(wanted) == check['rows']
                assert {r[idcol] for r in records} == wanted
                for row in records:
                    for col in check['label_columns_checked']:
                        assert int(row[col]) == int(can[row[idcol]]['label_int']), member
        heldout = read_csv(io.StringIO(z.read('source_holdout/final/s9g2_guo_to_datadog_partial_ood_predictions.csv').decode('utf-8-sig')))
        population = read_csv(io.StringIO(z.read('source_holdout/populations/datadog_ood_evaluation.csv').decode('utf-8-sig')))
        ids = {r['sample_id'] for r in population}
        assert len(ids) == 1348 and len(heldout) == 4044
        for seed in ('1001','1002','1003'):
            part = [r for r in heldout if r['seed'] == seed]
            assert len(part) == 1348 and {r['sample_id'] for r in part} == ids
            assert all(int(r['y_true']) == int(can[r['sample_id']]['label_int']) for r in part)
    print(f'PASS: {len(members)} saved-output members; source hashes and saved population identities')
    print('VirusTotal: sealed aggregate only; no row-level reconstruction performed.')


if __name__ == '__main__':
    verify_saved_outputs(Path(__file__).resolve().parents[1])
