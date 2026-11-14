#!/usr/bin/env python3
"""Plan or fetch exact original package archives; never extract or execute them."""
import argparse
import csv
import hashlib
import json
import re
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_HOSTS = {"files.pythonhosted.org", "raw.githubusercontent.com"}


def checked_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError(f"Not an approved original-source URL: {url}")
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def target_name(row):
    original = re.sub(r"[^A-Za-z0-9._-]", "_", Path(row["archive_filename"]).name)
    original = original[:150] or "archive.bin"
    return row["archive_sha256"] + "--" + original


def download_one(row, output, opener, timeout):
    url = checked_url(row["archive_download_reference"])
    expected = row["archive_sha256"]
    size = int(row["archive_size_bytes"])
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or size <= 0:
        raise ValueError(f"Invalid archive identity: {row['sample_id']}")
    destination = output / target_name(row)
    if destination.exists():
        if destination.stat().st_size == size and digest(destination) == expected:
            return {"status": "verified_existing", "path": destination.name, "bytes": size, "sha256": expected}
        raise ValueError(f"Existing file has a different identity; not overwritten: {destination}")
    temporary = None
    try:
        sha = hashlib.sha256()
        received = 0
        request = urllib.request.Request(url, headers={"User-Agent": "PSHGuard-research-input-check/1.0",
                                                       "Accept-Encoding": "identity"})
        with opener.open(request, timeout=timeout) as response:
            checked_url(response.geturl())
            with tempfile.NamedTemporaryFile(dir=output, prefix=".download-", suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > size:
                        raise ValueError("Response exceeds the frozen archive size")
                    sha.update(block)
                    handle.write(block)
        if received != size or sha.hexdigest() != expected:
            raise ValueError(f"Archive size/SHA256 differs from frozen input: {row['sample_id']}")
        # An exclusive new file prevents an accidental overwrite in a shared output directory.
        with temporary.open("rb") as source, destination.open("xb") as target:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                target.write(block)
        return {"status": "downloaded_and_verified", "path": destination.name,
                "bytes": received, "sha256": expected}
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ROOT, help="Repository root containing data/ and metadata/ (default: this repository)")
    parser.add_argument("--sample-id", action="append", default=[], help="Repeat to select exact sample IDs")
    parser.add_argument("--split", choices=("train", "val", "test"))
    parser.add_argument("--all", action="store_true", help="Select every record (12.23 GB in total)")
    parser.add_argument("--download", action="store_true", help="Otherwise print a plan without network access")
    parser.add_argument("--output", type=Path, help="New/existing storage folder outside the checked repository")
    parser.add_argument("--report", type=Path, help="New JSON report file; never overwritten")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    with (artifact / "data/access/ORIGINAL_PACKAGE_ACCESS.csv").open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    ids = {r["sample_id"] for r in all_rows}
    unknown = set(args.sample_id) - ids
    if unknown:
        parser.error("Unknown sample ID(s): " + ", ".join(sorted(unknown)))
    if args.all and (args.sample_id or args.split):
        parser.error("Use --all separately from --sample-id/--split")
    selected = [r for r in all_rows
                if (not args.sample_id or r["sample_id"] in args.sample_id)
                and (not args.split or r["split"] == args.split)]
    if args.download and not (args.sample_id or args.split or args.all):
        parser.error("Explicitly select --sample-id, --split, or --all before downloading")
    if args.download and not args.output:
        parser.error("--download requires --output")
    if args.retries < 0 or args.timeout <= 0:
        parser.error("Retries must be nonnegative and timeout must be positive")
    if args.report and args.report.exists():
        parser.error("The requested report already exists; choose a new filename")
    for row in selected:
        checked_url(row["archive_download_reference"])
    report = {"mode": "download" if args.download else "plan_only_no_network",
              "utc_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "selected_samples": len(selected),
              "expected_bytes": sum(int(r["archive_size_bytes"]) for r in selected),
              "retrieval_channels": dict(Counter(r["source_kind"] for r in selected)),
              "payloads_extracted_or_executed": False, "records": []}
    failures = 0
    if args.download:
        output = args.output.expanduser().resolve()
        if output == artifact or artifact in output.parents:
            parser.error("Store original inputs outside the checked repository directory")
        output.mkdir(parents=True, exist_ok=True)
        opener = urllib.request.build_opener(CheckedRedirect())
        for row in selected:
            record = {"sample_id": row["sample_id"], "url": row["archive_download_reference"]}
            for attempt in range(args.retries + 1):
                try:
                    record.update(download_one(row, output, opener, args.timeout))
                    break
                except Exception as exc:
                    if attempt == args.retries:
                        record.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
                        failures += 1
                    else:
                        time.sleep(min(2 ** attempt, 4))
            report["records"].append(record)
        report["failed_samples"] = failures
    elif len(selected) <= 20:
        report["records"] = [{"sample_id": r["sample_id"], "url": r["archive_download_reference"],
                               "expected_bytes": int(r["archive_size_bytes"]),
                               "sha256": r["archive_sha256"]} for r in selected]
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    print(rendered, end="")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
