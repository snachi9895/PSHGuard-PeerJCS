# Release-readiness status

Local preparation candidate v4 includes code, frozen data identities, saved experiment outputs and plotting source data. The separate model record is published at https://doi.org/10.5281/zenodo.24038283. The code/data repository was Private in the latest supplied screenshot; this candidate has not been uploaded and has no code/data DOI yet.

## Prepared and checked

- Frozen 20,878-record split and original-input access index, with dated 2026-11-07 checks. The checks combine PyPI metadata/HEAD, 30 full CDN SHA256 matches and fixed Git-tree/local-blob matches; they are not a full remote redownload of every input.
- Final-test, validation, budget and source/size outputs, plus a member-indexed bundle of saved ablation, efficiency, perturbation, holdout, calibration and comparator records.
- Exact original files and reported result identities; no training, inference, calibration, bootstrap or scientific metric recomputation during preparation.
- Author-approved MIT for author-owned code/documentation; preserved upstream terms; separate MIT/Apache-2.0 model grants.
- No-download distribution/hash/identity verifier and an optional model-ZIP checksum tool. Historical environment and implementation entry points are documented.

## Before final journal submission

1. Upload this candidate to the dedicated GitHub repository and verify a downloaded copy. Then make the intended code/data version accessible and archive that exact version with a real code/data DOI. The existing DOI covers models only.
2. Synchronize the author-approved Chinese revisions into the English manuscript, then confirm the final manuscript/result index and matching availability statements.
3. Full reconstruction still requires the original archives, generation of graph/token caches and a suitable recorded environment. Archived research entry points retain their original workspace conventions. The inspection commands are tested; an end-to-end training/inference reconstruction has not been run during this task.
4. Preserve the documented VirusTotal aggregate-only scope. Do not state that all seven comparators can be recomputed from distributed row-level outputs. If the journal requires further material, resolve that exact request from frozen source evidence.

The upstream raw archives keep their original terms. Persistent source references and checksums identify them; this package assigns no blanket redistribution licence to third-party payloads. This readiness record describes actual materials and checks, not an editorial acceptance decision.
