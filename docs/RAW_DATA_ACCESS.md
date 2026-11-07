# Original package access index

data/access/ORIGINAL_PACKAGE_ACCESS.csv identifies the original 20,878 package archives used by the frozen experiments. It does not contain package payloads or replace their upstream terms.

- 10,643 benign archives: official PyPI JSON metadata lookup by the recorded name and version. Select the source filename with exactly the archive_sha256 listed here.
- 8,114 archives: hash-matched Guo registry paths at source commit 5f33333e64aa384ab12e707c7eb5f4f6d1acf25a.
- 2,121 archives: Datadog dataset paths at source commit bd451196cdc0ef299e147c9b1a793ede76637d08.

These are retrieval-channel counts. Source-list labels remain 9,173 Guo and 1,062 Datadog malicious records. Of the Guo-list records, 1,059 use Datadog archive paths. No labels, splits, scores or scientific results were changed.

Every record retains its original package/version, sample ID and SHA256. All 10,235 malicious-archive paths were checked against the locally frozen upstream Git trees, using NUL-delimited names to preserve non-ASCII characters. Benign API URLs and source Git paths are access references; live archive retrieval was not tested, and no sample URLs were accessed in this audit.

Datadog declares Apache-2.0 for its dataset. No blanket licence was identified at the used Guo snapshot's root. Follow upstream terms and original package rights. This project does not apply its code licence to third-party archive contents.

If an upstream URL is unavailable, record the exact affected sample IDs and hashes and resolve their access route before claiming unrestricted access. The index alone is not a substitute for available raw inputs required by the target journal.

## Columns and verification

The row key is sample_id. package_name, version, label_int, split and archive_sha256 match the frozen data/manifests/ shards. archive_size_bytes and archive_filename describe the stored original archive. source_repository, source_revision, source_relative_path and source_url identify its upstream access reference. source_path_tracked_at_revision records a local Git-tree metadata check for malicious archives, not a network-download check. For PyPI records, retrieve the JSON metadata and select the exact source filename/SHA256 rather than substituting a newer release.

recorded_sample_namespace and manifest_source_group preserve different existing provenance fields; neither is reassigned based on the retrieval channel. See the source-list versus retrieval counts above.

The standard-library verifier checks row identity and URL construction without any network requests. It does not install, run or download original packages. The archive bytes and the six research checkpoints remain outside this compact preparation distribution.
