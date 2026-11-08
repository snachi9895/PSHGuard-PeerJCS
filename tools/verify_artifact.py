#!/usr/bin/env python3
"""Local-only audit of files and saved aggregate identities; standard library only."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import hashlib
import json
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def read_rows(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    files = read_rows(ROOT / 'metadata/FILE_SHA256.csv')
    names = set()
    for r in files:
        rel = Path(r['path'])
        assert not rel.is_absolute() and '..' not in rel.parts and r['path'] not in names
        names.add(r['path'])
        f = ROOT / rel
        assert f.is_file() and f.stat().st_size == int(r['bytes']), r['path']
        assert hashlib.sha256(f.read_bytes()).hexdigest() == r['sha256'], r['path']
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()
              and '.git' not in p.relative_to(ROOT).parts and '__pycache__' not in p.relative_to(ROOT).parts
              and p.relative_to(ROOT).as_posix() != 'metadata/FILE_SHA256.csv'}
    assert actual == names, (actual-names, names-actual)
    split = Counter()
    manifest_by_id = {}
    seen = set()
    components = defaultdict(set)
    sizes = Counter()
    for p in sorted((ROOT / 'data/manifests').glob('*.part-*.csv')):
        for r in read_rows(p):
            assert r['sample_id'] and r['sample_id'] not in seen
            seen.add(r['sample_id'])
            manifest_by_id[r['sample_id']] = r
            split[r['split']] += 1
            components[r['source_clone_component_id']].add(r['split'])
            sizes[r['source_clone_component_id']] += 1
    assert len(seen)==20878 and split=={'train':16613,'val':2137,'test':2128}, split
    assert len(components)==11813 and all(len(v)==1 for v in components.values())
    assert max(sizes.values())==5319
    assert all(components[k]=={'train'} for k,v in sizes.items() if v>50)
    tab = read_rows(ROOT / 'results/current/table_01_existing_detectors.csv')
    assert len(tab)==8 and not any(r['method'].endswith('-only') for r in tab)
    assert {r['method'] for r in tab}=={'Bandit4Mal','GuardDog','OSSGadget','VirusTotal','Cerebro','EA4MP','PyPIMalDet','PSHGuard'}
    psh = next(r for r in tab if r['method']=='PSHGuard')
    assert psh['F1_percent_display']=='92.538' and psh['F1_sd_pp_display']=='1.238'
    assert len(read_rows(ROOT/'results/current/table_02_graph_representation.csv'))==16
    budget = read_rows(ROOT/'results/file_budget/all_budgets_mean_sample_sd.csv')
    assert {int(r['budget']) for r in budget}=={4,8,16,32}
    assert all(int(r['runs'])==3 for r in budget)
    paired = read_rows(ROOT/'results/current/figure_03_paired_branch_differences.csv')
    mb = next(r for r in paired if r['contrast']=='f1_fusion_minus_modernbert')
    assert float(mb['ci95_lower_ratio'])<0<float(mb['ci95_upper_ratio'])
    t3 = read_rows(ROOT/'results/current/table_03_auroc_and_fpr.csv')
    dd = [r for r in t3 if r['contrast']=='datadog_vs_benign' and r['view']=='retained_overlap_weighted']
    assert len(dd)==5 and all(r['ci95_lower']=='' and r['ci95_upper']=='' for r in dd)
    access = read_rows(ROOT / 'data/access/ORIGINAL_PACKAGE_ACCESS.csv')
    assert len(access) == len(manifest_by_id) == 20878
    assert {r['sample_id'] for r in access} == set(manifest_by_id)
    for r in access:
        original = manifest_by_id[r['sample_id']]
        for key in ('package_name', 'version', 'label_int', 'split', 'archive_sha256'):
            assert r[key] == original[key], (r['sample_id'], key)
        assert r['manifest_source_group'] == original['source_group']
        assert len(r['archive_sha256']) == 64
        assert int(r['archive_size_bytes']) > 0
        parsed = urlsplit(r['source_url'])
        assert parsed.scheme == 'https'
        if parsed.netloc == 'github.com':
            expected = r['source_repository'].rstrip('/') + '/blob/' + r['source_revision'] + '/' + quote(r['source_relative_path'], safe='/')
            assert r['source_path_tracked_at_revision'].lower() == 'true'
        else:
            assert parsed.netloc == 'pypi.org'
            expected = 'https://pypi.org/pypi/' + quote(r['package_name'], safe='') + '/' + quote(r['version'], safe='') + '/json'
        assert r['source_url'] == expected, (r['sample_id'], 'access reference')
    models = read_rows(ROOT / 'metadata/MODEL_ACCESS_PLAN.csv')
    assert len(models) == 11
    assert {(r['role'], r['seed']) for r in models if r['role'].startswith('pshguard_')} == {(role, str(seed)) for role in ('pshguard_hgt', 'pshguard_modernbert_finetuned') for seed in (1001, 1002, 1003)}
    licence = json.loads((ROOT / 'metadata/LICENSE_STATUS.json').read_text(encoding='utf-8'))
    assert licence['software_licence'] == 'MIT' and licence['main_code_rights_confirmed']
    assert not licence['data_and_weights_licence_assigned_by_this_update']
    assert (ROOT / 'LICENSE').read_text(encoding='utf-8').startswith('MIT License\n')
    live = json.loads((ROOT / 'data/access/LIVE_ACCESS_SUMMARY.json').read_text(encoding='utf-8'))
    assert live['access_check_counts'] == {'pypi_json_sha256_and_cdn_head': 10613, 'pypi_cdn_streamed_sha256': 30, 'remote_git_tree_and_local_blob_hash': 10235}
    assert Counter(r['access_check_scope'] for r in access) == live['access_check_counts']
    assert all(r['access_checked_date'] == '2026-11-07' for r in access)
    assert all(urlsplit(r['archive_download_reference']).scheme == 'https' for r in access)
    binding = json.loads((ROOT / 'metadata/FINAL_HGT_SOURCE_BINDING.json').read_text(encoding='utf-8'))
    assert all((ROOT / rel).is_file() for rel in binding['static_import_closure_files'])
    for binding_check in binding['training_source_hash_checks']:
        assert hashlib.sha256((ROOT / binding_check['path']).read_bytes()).hexdigest() == binding_check['sha256']
    attachment = json.loads((ROOT / 'metadata/MODEL_ATTACHMENT.json').read_text(encoding='utf-8'))
    assert attachment['hgt_weights_licence'] == 'MIT' and attachment['modernbert_finetune_licence'] == 'Apache-2.0'
    assert attachment['public_url'] == 'https://zenodo.org/records/24038283' and attachment['doi'] == '10.5281/zenodo.24038283'
    from verify_saved_outputs import verify_saved_outputs
    verify_saved_outputs(ROOT)
    print(f'PASS: {len(access)} original-archive access identities; no URL requests')
    print('PASS: MIT scope metadata and 11 model/config access-plan records')
    print(f'PASS: {len(files)} checksummed files; complete distribution inventory verified')
    print(f'PASS: {len(seen)} unique samples; splits={dict(split)}; {len(components)} isolated components')
    print('PASS: current table/figure identities, four budgets, and saved missing/uncertainty states')
    print('No training, prediction replay, calibration fit, bootstrap, or network access performed.')


if __name__ == '__main__':
    main()
