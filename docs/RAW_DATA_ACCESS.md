# Original package access index

data/access/ORIGINAL_PACKAGE_ACCESS.csv identifies the original 20,878 package archives used by the frozen experiments. It does not contain package payloads or replace their upstream terms.

- 10,643 benign archives: official PyPI JSON metadata lookup by the recorded name and version. Select the source filename with exactly the archive_sha256 listed here.
- 8,114 archives: hash-matched Guo registry paths at source commit 5f33333e64aa384ab12e707c7eb5f4f6d1acf25a.
- 2,121 archives: Datadog dataset paths at source commit bd451196cdc0ef299e147c9b1a793ede76637d08.

These are retrieval-channel counts. Source-list labels remain 9,173 Guo and 1,062 Datadog malicious records. Of the Guo-list records, 1,059 use Datadog archive paths. No labels, splits, scores or scientific results were changed.

Every record retains its original package/version, sample ID and SHA256. All 10,235 malicious-archive paths were checked against the locally frozen upstream Git trees, using NUL-delimited names to preserve non-ASCII characters. The initial preparation checked local metadata only. The subsequent dated live checks are reported below; their scopes are recorded separately rather than replacing the historical source fields.

Datadog declares Apache-2.0 for its dataset. No blanket licence was identified at the used Guo snapshot's root. Follow upstream terms and original package rights. This project does not apply its code licence to third-party archive contents.

If an upstream URL is unavailable, record the exact affected sample IDs and hashes and resolve their access route before claiming unrestricted access. The index alone is not a substitute for available raw inputs required by the target journal.

## Live access checks on 2026-11-07

The new archive_download_reference column identifies the fixed original-file reference; source_url preserves the original metadata/registry reference and is not overwritten. For 10,613 PyPI inputs, the release JSON advertises the frozen SHA256/size and the original CDN file returns HTTP 200 with the expected Content-Length. For the other 30, a fixed official CDN address was recovered from the original archive identity and its full remote bytes were streamed and SHA256/size verified. These 30 include 26 release metadata 404s, one old digest absent from the returned release, and three initial network/parse errors. No replacement release, new label or new sample was substituted.

The two fixed malicious-source commits were fetched as blob-filtered Git metadata; remote trees match the frozen trees. All 10,235 original local malicious archives were read for SHA256 and Git blob identity, matching the objects referenced by the fetched trees. Their raw HTTP references are constructed from those verified trees; this is not a claim that every raw endpoint was individually downloaded.

All 20,878 local original archives (12,226,308,159 bytes) match their existing SHA256 and size. The audit read archive bytes for hashing only. It did not extract, install or execute packages. Summary and scope: data/access/LIVE_ACCESS_SUMMARY.json.

## Columns and verification

The row key is sample_id. package_name, version, label_int, split and archive_sha256 match the frozen data/manifests/ shards. archive_size_bytes and archive_filename describe the stored original archive. source_repository, source_revision, source_relative_path and source_url identify its upstream access reference. source_path_tracked_at_revision records a local Git-tree metadata check for malicious archives, not a network-download check. For PyPI records, retrieve the JSON metadata and select the exact source filename/SHA256 rather than substituting a newer release.

recorded_sample_namespace and manifest_source_group preserve different existing provenance fields; neither is reassigned based on the retrieval channel. See the source-list versus retrieval counts above.

The standard-library verifier checks row identity and URL construction without any network requests. It does not install, run or download original packages. Original archive bodies remain external. The six author-licensed research checkpoints are published as a separate model attachment; see docs/MODEL_ATTACHMENT.md.

## Repository-root retrieval utilities (14 November 2026)

The current README links both public version 1.0.0 archives: code/supporting data at https://doi.org/10.5281/zenodo.24048825 and models at https://doi.org/10.5281/zenodo.24038283. These fixed archives retain their original files. This GitHub documentation update adds retrieval/inspection utilities without changing the source access records.

Run from the repository root (Python 3.10+; standard library only):

```text
python3 -B tools/fetch_original_archives.py
python3 -B tools/fetch_original_archives.py --sample-id benign__aiochannel__1.3.0
```

These commands display plans and make no network requests. To retrieve exact original bytes and check the frozen hash/size:

```text
python3 -B tools/fetch_original_archives.py --sample-id benign__aiochannel__1.3.0 --download --output ../PSHGuard_review_work/original_archives --report ../PSHGuard_review_work/one_input.json
```

Repeat `--sample-id`, select `--split train` / `val` / `test`, or explicitly use `--all` for the full corpus. Full download transfers about 12.23 GB. Use a storage directory outside the repository. The tool accepts fixed approved HTTPS original-source references, validates redirects, records failures by sample ID, checks size and SHA256, and does not substitute later versions. It stores compressed bytes without extracting, installing or executing package contents. Some samples contain malicious code; do not install or execute them.

The fields `archive_download_reference` and `source_url` serve different purposes: the first is the exact file-download reference; the second retains the source metadata/registry reference. SHA256 identifies the original bytes and does not preserve a file that is later removed upstream. Report any missing file by sample ID and expected hash so its access route can be resolved.

The corpus-level split/source data, saved predictions and numerical figure inputs are distributed directly in this repository. Their dictionaries, units and reporting populations are described in docs/DATA_DICTIONARY.md, docs/PREDICTION_FILES.md and docs/PAPER_RESULT_INDEX.md. The original package access index is not claimed to contain the raw package payloads.
