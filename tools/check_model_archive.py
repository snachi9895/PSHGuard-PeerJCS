#!/usr/bin/env python3
"""Hash a manually downloaded model ZIP without loading model code or weights."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    expected = json.loads((Path(__file__).resolve().parents[1]/'metadata/MODEL_ATTACHMENT.json').read_text())
    if not args.archive.is_file() or args.archive.stat().st_size != expected['bytes']:
        raise SystemExit('FAIL: model archive missing or byte count differs')
    h = hashlib.sha256()
    with args.archive.open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    if h.hexdigest() != expected['sha256']:
        raise SystemExit('FAIL: model archive SHA256 differs')
    print('PASS: model ZIP bytes match published version ' + expected['doi'])
    print('No extraction, model deserialization, inference or network request performed.')


if __name__ == '__main__':
    main()
