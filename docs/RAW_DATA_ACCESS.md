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
