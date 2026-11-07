# Release-readiness status

This is private preparation draft v2. Selecting a software licence does not itself make the repository public or DOI-archived. The manuscript availability statements have not yet been updated to claim either status.

## Available now

- Frozen split metadata, implementation entry points, saved aggregate results and exact data/plotting code for Figures 3-7.
- Saved proposed-model final-test/validation predictions, four-budget OOF tables and selected statistical arrays/replicates.
- File hashes, source-copy ledger, standard-library verifier and historical environment records.
- Author-confirmed MIT licence for author-owned code/documentation, defined scope and preserved third-party notices.
- Original package access index: 20,878 frozen identities; all 10,235 malicious-archive paths checked in the locally fixed upstream Git trees. PyPI entries are exact name/version metadata lookups with required archive SHA256.
- Model access plan: six research checkpoints (about 1.80 GB), pinned ModernBERT base model and four config/tokenizer files. Weights are not bundled.

## Resolve before public journal release

1. Original package archives: verify that the documented upstream routes actually supply the exact inputs and resolve any access/redistribution restrictions. Local Git-tree and identity checks are not live-download checks; the journal's raw-data requirement is not automatically waived for malware samples or large files.
2. Weights/caches: complete the archive/access plan in metadata/MODEL_ACCESS_PLAN.csv and metadata/EXTERNAL_MODEL_INVENTORY.json, retain applicable upstream terms, and provide or reconstruct derived representations needed by portable commands. Software MIT does not grant a model/data licence.
3. Figure/table dependency coverage: audit the remaining ablation, perturbation, holdout and external-baseline raw inputs. The saved S10 identity audit records VirusTotal as aggregate-only; do not invent row-level predictions.
4. Third-party references: retain current notices and complete accurate persistent identifiers where available. Source links are not new redistribution permission.
5. Reproduction instructions: validate portable commands against the actual distributed scope. Archived scripts with absent inputs are not a tested end-to-end pipeline.
6. Manuscript identity: synchronize author-approved Chinese revisions into the English manuscript and freeze the final result/figure index.
7. Permanent access: after contents and scope are confirmed, create an accessible versioned archive/DOI and test access, then update manuscript availability statements to match the real files and identifiers.

No new model fit, formal-test rerun, calibration, bootstrap, repository visibility change or DOI registration was performed to prepare this update.
