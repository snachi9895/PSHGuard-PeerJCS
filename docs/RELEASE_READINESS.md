# Current distribution and reproduction status

Updated 14 November 2026 for PeerJ Computer Science manuscript 152920.

## Public resources

- The GitHub repository is public. The original research snapshot is commit f91cad4f9635505d66ca7b699edf1580f5a3c96c.
- Code and supporting data are archived as version 1.0.0 at https://doi.org/10.5281/zenodo.24048825.
- Six trained model checkpoints and configurations are archived separately as version 1.0.0 at https://doi.org/10.5281/zenodo.24038283.
- The current branch adds a fuller repository-root README and review utilities. The published archives retain their original files; these fixed DOIs do not identify the later documentation changes.
- A dated README and compact code/data review companion are also supplied in the manuscript's supplemental files. Their `artifact/` layout is distinct from this repository-root layout.

## What the current update covers

README.md, docs/RAW_DATA_ACCESS.md and this status document are updated; tools/review_data.py and tools/fetch_original_archives.py are added. metadata/FILE_SHA256.csv is regenerated for the resulting complete repository inventory. Historical provenance records retain their original preparation dates/statuses.

The scientific implementations, sample labels, fixed partitions, model configurations, trained weights, saved predictions, statistics and figure-source numerical data are unchanged. The new review utilities read those existing files and support inspection, exact-input retrieval and recalculation of saved point metrics.

## Checks and reproduction scope

- The repository verifier checks the full recorded file inventory, 20,878 sample/access identities, 11,813 component-disjoint groups, source bindings and saved reporting contracts.
- Review commands load the frozen sample table and recalculate point metrics from the nine saved internal-branch prediction files; they do not perform new training, new inference, calibration fitting, threshold selection or bootstrap generation.
- Original package payloads are obtained from the fixed upstream references and checked by size and SHA256. The 7 November access audit has its original metadata/CDN/tree/local-hash scope; the 14 November companion check retrieved one file from each of three channels. Neither is described as a fresh full-corpus redownload on 14 November.
- Full pipeline reconstruction additionally requires original archives, generated graph/token caches, pinned model/base-model resources and the recorded environment. Research entry points retain historical workspace/path conventions. A new clean-environment end-to-end retraining/inference run is not claimed by this update.
- The formal VirusTotal comparator is preserved as an aggregate-only result. Per-package VirusTotal reports or predictions are not reconstructed.

## Journal submission status and third-party terms

These are documentation/access arrangements for a manuscript submission, not an editorial acceptance decision. Original third-party data use fixed public-source access routes; an index is not a mirror of the package payloads. Any failed exact-input reference must be resolved rather than replaced with a different package version. MIT covers author-owned code/documentation only; source-specific and package-specific rights remain applicable. See docs/RAW_DATA_ACCESS.md and docs/LICENSE_SCOPE.md.
