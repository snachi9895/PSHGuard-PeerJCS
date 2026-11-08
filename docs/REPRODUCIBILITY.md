# Reproducibility and reporting

## Checks available in this candidate

Run python3 tools/verify_artifact.py for a no-download integrity check. The package contains the frozen split metadata, saved aggregate results, final-test/validation prediction tables and the supplemental saved-output bundle, statistical outputs, and exact source files for the data figures.

This task copied saved results and checked identities only. It did not rerun the formal test, fit calibration or fusion, bootstrap statistics, or model inference.

## Data figure source

figure_source/v3/generate_figures.py is copied without modification. It reads its adjacent data/ files and generates Figures 3-7. The original implementation uses Arial from a Windows font installation, matplotlib and numpy. No font files are redistributed, and no figure was regenerated in this packaging task.

## Original inputs and model access

data/access/ORIGINAL_PACKAGE_ACCESS.csv maps all frozen sample identities to original-archive access references; docs/RAW_DATA_ACCESS.md explains the fields and local-only checks. metadata/MODEL_ACCESS_PLAN.csv identifies the six research checkpoints and the pinned base-model/config dependencies. Dated input-access evidence is recorded in data/access/LIVE_ACCESS_SUMMARY.json. The model attachment is published at https://doi.org/10.5281/zenodo.24038283 with author-confirmed licences; raw archives, weight binaries and representation caches are not bundled in this compact code snapshot. No end-to-end run is claimed. See docs/SAVED_OUTPUTS.md for diagnostic/comparator coverage and its aggregate-only VirusTotal scope.

## Remaining reconstruction work

The archived entry points below retain the historical workspace layout and are not a single ready-to-run installation command. Original package archives, graph/token caches and model weights remain external. Dependency details are in docs/RECORDED_ENVIRONMENTS.md; the broad requirements file is not a newly tested exact lockfile. See docs/RELEASE_READINESS.md before describing the draft as a complete end-to-end reproduction package.

## Frozen implementation entry points

- Final six-relation grouping and exact-V2 split: `scripts/final_source_clone_split_20260611/step09_build_final_source_clone_aware_graph_eligible_v2_strict40.py`; independent split audit: `step10_audit_frozen_graph_eligible_v2_strict40.py` in that directory.
- Graph representation: `scripts/final_graph_v10c_full_20260612/step02_v10c_full_export_pipeline.py` and its retained dependencies.
- Final HGT practical paired-run entry point: `scripts/formal_training_v10c_20260612/train_p3_rcber_paired_hgt_v2.py` with model kind practical; `train_v10c_formal_hgt.py` remains a retained base trainer. The local import closure and recorded source bindings are in metadata/FINAL_HGT_SOURCE_BINDING.json.
- Sequence extraction/training: `build_s1_base_modernbert_cache.py`, `run_s1_base_modernbert_screen.py`, and `run_s1_base_modernbert_confirmatory.py` in that directory.
- Same-seed fusion: `scripts/formal_training_v10c_20260612/audit_s8a_same_seed_paired_fusion.py`.
- Later descriptive aggregation: `research_state/single_hgt_ablation_reporting_20261021/scripts/summarize_saved_metrics.py`.
- Budget replay and verification: `research_state/file_budget_same_seed_fusion_replay_20261026/`.
- Joint-size analysis and verification: `paper1015-Frontiers/analysis/scripts/` with its frozen protocol in the adjacent `protocols/` directory.

These are archived scientific entry points, not setup commands to execute on the published snapshot. Their original inputs/outputs are workspace-relative and include generated files excluded here. The shortened `results/` paths are a distribution layout; `metadata/SOURCE_COPY_MAP.csv` maps them back to the saved workspace paths. Follow source code and specifications when reconstructing a separate full workspace.

## Scientific contracts

- Paired system seeds: 1001–1003. Each system contains one graph model and one same-seed sequence model.
- Primary graph-file limit: 16; token input: 512, including special tokens (at most 510 content tokens).
- Fusion: validation-only standardization and L2-regularized logistic regression. Validation OOF and frozen final-test deployment fits are different evaluation objects.
- Table II A: raw AP of single HGT models and their calibrated validation OOF classification F1; three-run mean and sample SD.
- Table II B and Fig.4(a): one HGT plus one same-seed ModernBERT; saved OOF ablation summaries and their matching saved intervals.
- Fig.4(b): current dual-branch budget results, three-run mean/sample SD. No new confidence intervals were computed for this budget comparison.
- Earlier three-HGT ensemble classifications in historical audits are auxiliary systems and do not replace current Table II A or dual-branch budgets.
- Table III: post hoc validation diagnosis conditional on stored scores/decisions. Fixed LR is one training fit. Joint-size weighting changes evaluation weights, not models or operating points. Datadog weighted intervals are missing under the fixed valid-draw rule.
- Final-test branch differences use saved point deltas and paired seed/component intervals; bootstrap means are not substituted for observed point deltas.

Historical README/spec files may contain prospective phrases such as “test locked” or “will be used.” Their timestamps and freeze status describe the stage when written. The completed reported experiments are preserved, and this distribution does not authorize reopening them.

## Environment and external artifacts

`docs/RECORDED_ENVIRONMENTS.md` records the historical versions. `requirements.txt` contains broad compatibility ranges, not an exact lockfile or a claim that an installation was tested in this packaging task. CUDA/PyTorch builds and the pinned ModernBERT revision require separate acquisition. The original implementation supports `PSHGUARD_ROOT` for workspace configuration where provided by a script; inspect each entry point before use.

No experiment, calibration/threshold fit, model inference, or bootstrap was run to create this distribution. The validation budget fits were completed in the separately frozen October analysis; this package copies their saved summaries.

## Optional model-file check

After manually downloading the published model ZIP, run `python3 tools/check_model_archive.py /path/to/model.zip`. This checks the full ZIP size and SHA256 without extracting or deserializing a checkpoint. The default artifact verifier does not require the 1.80 GB file and makes no network requests.
