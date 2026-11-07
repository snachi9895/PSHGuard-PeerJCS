# PSHGuard-PeerJCS

Code and supporting data for PSHGuard: Detecting Malicious PyPI Packages With Complementary Behavioral Views.

This is private preparation draft v2 for the PeerJ Computer Science manuscript. It contains frozen research implementation, package/split metadata, saved predictions, statistical outputs, and source data for the paper's data figures. No acceptance, public archival release, or DOI is claimed.

## Start here

1. docs/PAPER_RESULT_INDEX.md maps the 7 figures, 3 tables, and supporting analyses to files.
2. docs/REPRODUCIBILITY.md explains what can be checked now and what additional inputs are needed.
3. docs/DATA_DICTIONARY.md and docs/PREDICTION_FILES.md explain columns and reporting identities.
4. docs/RELEASE_READINESS.md lists items still to resolve before public release and journal submission.
5. docs/RAW_DATA_ACCESS.md explains the original-archive access index and its verification limits.
6. docs/LICENSE_SCOPE.md and docs/THIRD_PARTY_NOTICES.md explain MIT coverage and preserved third-party terms.

## Inspect the distribution

Run from this repository root:

    python3 tools/verify_artifact.py

The verifier checks file hashes, the 20,878-record split, and saved table identities. It performs no training, inference, calibration fit, bootstrap calculation, or downloads.

## Layout

| Directory | Contents |
| --- | --- |
| scripts/ and baselines/ | Archived implementation and retained import dependencies, in their original relative layout. |
| data/access/ | Exact source access references for all 20,878 original archives; payloads not bundled. |
| data/manifests/ | Eleven CSV shards with source identities, inherited labels, components and frozen splits. |
| data/predictions/ | Saved final-test and validation predictions, including all four graph-file budgets. |
| data/statistics/ | Saved paired-bootstrap outputs and final-test/source-size reports. |
| configs/ | Frozen validation-fitted deployment parameters. |
| results/ | Saved aggregate tables and diagnostics. |
| figure_source/v3/ | Unmodified PeerJ plotting implementation and exact CSV/JSON inputs for Figures 3-7. |
| research_state/ and paper1015-Frontiers/ | Archived later-analysis code and protocols; directory names record provenance. |
| third_party/ | Retained upstream dataset licence and notice. |
| docs/ and metadata/ | File mappings, data dictionary, provenance, checksums and release-readiness status. |

One HGT and one same-seed ModernBERT form each system; results summarize three runs. Training, validation and test records are separated by the defined project/code-clone components. Validation OOF scores and frozen final-test decisions are distinct evaluation objects.

## Scope

The compact package supports inspection of the implementation, preserved outputs and plotted numerical values. Full retraining and new inference additionally require the original package archives, derived representation caches, trained weights or reconstructed training, and the recorded environment. These large or third-party inputs are not included in this preparation draft. data/access/ORIGINAL_PACKAGE_ACCESS.csv records the original inputs and metadata/MODEL_ACCESS_PLAN.csv records the proposed model attachment scope. Local identity/path checks are complete; live access and remaining reconstruction work are listed in docs/RELEASE_READINESS.md.

No new experiment or scientific recalculation was performed to prepare this distribution. Resolve the remaining items in docs/RELEASE_READINESS.md before public journal release.

## Software licence

Author-owned PSHGuard software and associated documentation are licensed under MIT; see LICENSE and docs/LICENSE_SCOPE.md. Third-party packages, datasets, models and dependencies retain their original terms. Data/result artifacts and model weights are not relicensed by the software grant. See docs/THIRD_PARTY_NOTICES.md for attribution and scope.

