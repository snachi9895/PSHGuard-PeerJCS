# PSHGuard-PeerJCS

Code and supporting data for PSHGuard: Detecting Malicious PyPI Packages With Complementary Behavioral Views.

This is a private preparation draft for the PeerJ Computer Science manuscript. It contains frozen research implementation, package/split metadata, saved predictions, statistical outputs, and source data for the paper's data figures. No acceptance, public archival release, or DOI is claimed.

## Start here

1. docs/PAPER_RESULT_INDEX.md maps the 7 figures, 3 tables, and supporting analyses to files.
2. docs/REPRODUCIBILITY.md explains what can be checked now and what additional inputs are needed.
3. docs/DATA_DICTIONARY.md and docs/PREDICTION_FILES.md explain columns and reporting identities.
4. docs/RELEASE_READINESS.md lists items still to resolve before public release and journal submission.
5. docs/RIGHTS_AND_ATTRIBUTION.md records the current licensing and third-party status.

## Inspect the distribution

Run from this repository root:

    python3 tools/verify_artifact.py

The verifier checks file hashes, the 20,878-record split, and saved table identities. It performs no training, inference, calibration fit, bootstrap calculation, or downloads.

## Layout

| Directory | Contents |
| --- | --- |
| scripts/ and baselines/ | Archived implementation and retained import dependencies, in their original relative layout. |
| data/manifests/ | Eleven CSV shards with source identities, inherited labels, components and frozen splits. |
| data/predictions/ | Saved final-test and validation predictions, including all four graph-file budgets. |
| data/statistics/ | Saved paired-bootstrap outputs and final-test/source-size reports. |
| configs/ | Frozen validation-fitted deployment parameters. |
| results/ | Saved aggregate tables and diagnostics. |
| figure_source/v3/ | Unmodified PeerJ plotting implementation and exact CSV/JSON inputs for Figures 3-7. |
| research_state/ and paper1015-Frontiers/ | Archived later-analysis code and protocols; directory names record provenance. |
| docs/ and metadata/ | File mappings, data dictionary, provenance, checksums and release-readiness status. |

One HGT and one same-seed ModernBERT form each system; results summarize three runs. Training, validation and test records are separated by the defined project/code-clone components. Validation OOF scores and frozen final-test decisions are distinct evaluation objects.

## Scope

The compact package supports inspection of the implementation, preserved outputs and plotted numerical values. Full retraining and new inference additionally require the original package archives, derived representation caches, trained weights or reconstructed training, and the recorded environment. These large or third-party inputs are not included in this preparation draft. Their access and redistribution plan is not yet finalized.

No new experiment or scientific recalculation was performed to prepare this distribution. No blanket software licence has yet been assigned. Preserve third-party notices and resolve the items in docs/RELEASE_READINESS.md before public release.
