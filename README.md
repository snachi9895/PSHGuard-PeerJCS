# PSHGuard: detecting malicious PyPI packages with complementary behavioral views

PSHGuard detects malicious Python Package Index (PyPI) packages through static analysis. It combines a package-level heterogeneous behavior graph with an independently extracted behavior sequence. Typed package context and local operation order provide complementary evidence for package risk ranking and screening before installation.

This repository contains the research implementation, frozen sample identities and partitions, saved predictions and statistical results, and the numerical data used in the manuscript figures. It accompanies PeerJ Computer Science manuscript **152920**; an accepted or published journal article is not claimed.

## 1. Published resources and version identity

| Resource | Version / identity | Location |
| --- | --- | --- |
| Frozen research code and supporting data | Version 1.0.0; GitHub snapshot `f91cad4f9635505d66ca7b699edf1580f5a3c96c` | [Zenodo: 10.5281/zenodo.24048825](https://doi.org/10.5281/zenodo.24048825) |
| Three HGT and three fine-tuned ModernBERT checkpoints, configurations and notices | Version 1.0.0; seeds 1001, 1002 and 1003 | [Zenodo: 10.5281/zenodo.24038283](https://doi.org/10.5281/zenodo.24038283) |
| Current code and documentation | This GitHub repository | [snachi9895/PSHGuard-PeerJCS](https://github.com/snachi9895/PSHGuard-PeerJCS) |

The repository documentation and two review utilities were updated on **14 November 2026**. The published version 1.0.0 archives remain the fixed research snapshots; their DOIs do not identify this later documentation update. Training/analysis implementations, labels, partitions, model configurations and saved research results are unchanged. `metadata/FILE_SHA256.csv` describes the files in the current repository.

Some provenance files retain preparation-time phrases such as "candidate v4", "Private", "DOI pending" or "English synchronization pending". They record the state when those files were written. The two published DOIs above and [the current distribution status](docs/RELEASE_READINESS.md) describe present access. These historical records have not been rewritten as new research results.

## 2. Dataset information

| Frozen corpus | Packages |
| --- | ---: |
| Training | 16,613 |
| Validation | 2,137 |
| Final test | 2,128 |
| Total | 20,878 |
| Benign / malicious labels | 10,643 / 10,235 |

Labels are inherited from the source collections. The 11,813 project/code-relatedness components are allocated intact to the three partitions. These relatedness components govern the split and are distinct from the per-package heterogeneous graphs used by the detector.

| Included data | Location |
| --- | --- |
| Sample identities, inherited labels, hashes, component assignments and fixed splits | [data/manifests](data/manifests): eleven CSV parts of one 20,878-row table, with a summary/part index |
| Exact original-file references, versions, filenames, sizes and SHA256 values | [data/access/ORIGINAL_PACKAGE_ACCESS.csv](data/access/ORIGINAL_PACKAGE_ACCESS.csv) |
| Saved final-test and validation predictions, including graph-file-budget runs | [data/predictions](data/predictions) |
| Saved statistical draws, tables and diagnostics | [data/statistics](data/statistics) and [results](results) |
| Numerical inputs and plotting source for Figures 3-7 | [figure_source/v3](figure_source/v3) |
| Additional saved ablation, efficiency, perturbation, holdout, calibration and comparator records | [data/supplementary](data/supplementary); see [saved-output coverage](docs/SAVED_OUTPUTS.md) |

CSV and JSON data can be read directly. A documented NumPy array additionally requires NumPy. See the [data dictionary](docs/DATA_DICTIONARY.md), [prediction-file definitions](docs/PREDICTION_FILES.md) and [paper-to-file index](docs/PAPER_RESULT_INDEX.md) for variables, units and the files supporting each figure and table.

### Original third-party package files

The original inputs are 20,878 compressed software-package archives totaling **12,226,308,159 bytes (about 12.23 GB)**. These payloads are obtained from their recorded public upstream sources rather than embedded in this compact repository or the code/data DOI archive. The per-file access index records the exact original file and its expected SHA256 and size; it is an access index, not a deposit of the original package bytes.

- Benign inputs use fixed official PyPI CDN file references.
- Malicious inputs use the [Guo registry at commit `5f33333e64aa384ab12e707c7eb5f4f6d1acf25a`](https://github.com/lxyeternal/pypi_malregistry/tree/5f33333e64aa384ab12e707c7eb5f4f6d1acf25a) or the [Datadog collection at commit `bd451196cdc0ef299e147c9b1a793ede76637d08`](https://github.com/DataDog/malicious-software-packages-dataset/tree/bd451196cdc0ef299e147c9b1a793ede76637d08).

The source-list counts are Guo 9,173 and Datadog 1,062 malicious samples. Download-channel counts are Guo 8,114 and Datadog 2,121 because 1,059 Guo-list samples were retrieved from Datadog paths. Preserve this distinction when interpreting source fields. Full access instructions and dated verification scopes are in [docs/RAW_DATA_ACCESS.md](docs/RAW_DATA_ACCESS.md).

The formal VirusTotal comparison is supplied as a frozen aggregate result; complete per-package VirusTotal reports are outside this distribution. The included saved predictions support checking the reported internal-system point metrics. Full retraining or new inference additionally requires the original inputs, generated graph/token caches, checkpoints and the recorded scientific environment.

## 3. Getting started: inspect and load the data

Clone this repository or download and extract its ZIP, then run the commands below **from the repository root**, where `data/`, `docs/` and `tools/` are located. These commands use **Python 3.10+ and its standard library**. On Windows, use a short extraction path such as `D:\PSHGuard-PeerJCS` to avoid long-path limitations. Substitute `python` for `python3` if that is your Python executable name.

Check the current repository file inventory, saved identities and source bindings:

```text
python3 -B tools/verify_artifact.py
```

Read all sample records, check access-index joins and confirm component-disjoint partitions:

```text
python3 -B tools/review_data.py --summary
```

Recalculate AP, AUROC, precision, recall, F1 and FPR from the nine saved graph/sequence/fusion final-test prediction files, and compare three-run means and sample standard deviations with the frozen tables:

```text
python3 -B tools/review_data.py --verify-metrics
```

Export the eleven sample-table parts into one new CSV, preserving every existing row and column:

```text
python3 -B tools/review_data.py --export-samples ../PSHGuard_review_work/samples_20878.csv
```

Outputs in these examples are outside the checked repository so that new files do not change its recorded inventory. In pandas, an individual table can be read with `pandas.read_csv("data/predictions/final_test/fusion_seed1001_test_predictions.csv")`. Join prediction and sample tables on `sample_id`, not on row position. The standard-library commands above require neither pandas nor a GPU.

### Retrieve an exact original input

The default command only displays a plan; it makes no network requests:

```text
python3 -B tools/fetch_original_archives.py
```

Inspect one exact sample's URL, hash and size:

```text
python3 -B tools/fetch_original_archives.py --sample-id benign__aiochannel__1.3.0
```

Download and verify that original file:

```text
python3 -B tools/fetch_original_archives.py --sample-id benign__aiochannel__1.3.0 --download --output ../PSHGuard_review_work/original_archives --report ../PSHGuard_review_work/one_input.json
```

Repeat `--sample-id` for selected inputs, use `--split train`, `--split val` or `--split test` for a partition, or explicitly use `--all` for the full corpus. Full download transfers about 12.23 GB. The tool checks SHA256 and size, reuses matching local files, records failures and rejects substituted versions. It stores compressed bytes only. Some samples contain malicious code: **do not install or execute the samples**.

The supplemental review companion supplied to PeerJ has its own dated README and places the original snapshot inside `artifact/`. The commands in this GitHub README are adapted to the repository-root layout and are not copied with that extra prefix.

## 4. Research code and implementation sequence

| Stage | Entry point / information |
| --- | --- |
| Construct relatedness components and the fixed split | `scripts/final_source_clone_split_20260611/step09_build_final_source_clone_aware_graph_eligible_v2_strict40.py`; audit with the adjacent `step10_audit_frozen_graph_eligible_v2_strict40.py` |
| Extract budget-controlled heterogeneous graphs | `scripts/final_graph_v10c_full_20260612/step02_v10c_full_export_pipeline.py` and retained dependencies |
| Train the practical HGT branch | `scripts/formal_training_v10c_20260612/train_p3_rcber_paired_hgt_v2.py`, model kind `practical`; see [HGT source bindings](metadata/FINAL_HGT_SOURCE_BINDING.json) |
| Build sequence caches and train ModernBERT | `build_s1_base_modernbert_cache.py`, `run_s1_base_modernbert_screen.py` and `run_s1_base_modernbert_confirmatory.py` under `scripts/formal_training_v10c_20260612/` |
| Fit same-seed validation-only fusion and evaluate frozen outputs | `scripts/formal_training_v10c_20260612/audit_s8a_same_seed_paired_fusion.py`; configurations in [configs](configs) |
| Inspect later analyses, file budgets and numerical figure inputs | [research_state](research_state), [paper1015-Frontiers/analysis](paper1015-Frontiers/analysis) and [figure_source/v3](figure_source/v3) |

For full reconstruction, first obtain the exact original input bytes and the required model/base-model resources, prepare the recorded environment, reconstruct graph/token caches using the extraction entry points, and follow the frozen training/validation/final-test sequence. Existing relatedness components and partitions can be loaded from the manifest. Historical directory names preserve provenance. Research entry points retain original workspace/path conventions; see [reproduction instructions](docs/REPRODUCIBILITY.md), [recorded environments](docs/RECORDED_ENVIRONMENTS.md) and [source-copy mappings](metadata/SOURCE_COPY_MAP.csv) before configuring those paths. A new clean-environment end-to-end retraining run is not claimed by this documentation update.

## 5. Requirements

- **Data inspection and review utilities:** Python 3.10+; standard library only. Reading the saved `.npz` array additionally requires NumPy.
- **Historical graph environment:** Python 3.10.20, NumPy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2, PyTorch `2.12.0.dev20260407+cu128`, PyTorch Geometric 2.7.0 and tqdm 4.67.3.
- **Historical sequence environment:** PyTorch `2.11.0+cu128`, transformers 4.57.6 and the recorded NumPy/pandas/scikit-learn versions above.
- **Figure-source plotting:** matplotlib and NumPy; the archived script uses an Arial font from a Windows installation. Font files are not redistributed.

[requirements.txt](requirements.txt) contains broad dependency ranges. [docs/RECORDED_ENVIRONMENTS.md](docs/RECORDED_ENVIRONMENTS.md) records the scientific environments; this update does not turn those ranges into a newly validated environment lockfile. The development PyTorch build and compatible CUDA setup may require separate acquisition.

## 6. Methodology and interpretation

Each reported system combines **one HGT graph branch and one same-seed ModernBERT sequence branch**; the reported results summarize three runs with seeds 1001-1003. Source-driven file ranking, semantic anchors and hierarchical node quotas define the graph input, with the adopted 16-file limit. The independently extracted sequence uses a 512-token limit, including special tokens. Validation-only standardization and L2-regularized logistic regression fuse the branch scores, and the deployment fit is frozen for final-test evaluation.

Keep validation out-of-fold results separate from final-test decisions. Numeric ratio metrics use `[0,1]`; percentages and percentage-point differences are explicitly labeled in manuscript tables. Three-run sample standard deviations and bootstrap confidence intervals describe different uncertainty summaries. Missing Datadog weighted intervals remain missing under the prespecified valid-draw rule. See the [paper-to-file index](docs/PAPER_RESULT_INDEX.md) for detailed evidence mappings.

## 7. Citation

Please cite the fixed resources actually used:

- Zhao, J.; Cui, M.; Tao, M.; Lu, Z.; Xiao, S. (2026). *PSHGuard: code and supporting data for malicious PyPI package detection*. Zenodo, version 1.0.0. https://doi.org/10.5281/zenodo.24048825
- Zhao, J.; Cui, M.; Tao, M.; Lu, Z.; Xiao, S. (2026). *PSHGuard: frozen model checkpoints and configurations*. Zenodo, version 1.0.0. https://doi.org/10.5281/zenodo.24038283

Upstream inputs retain their attribution to [PyPI](https://pypi.org/), the [Guo research collection](https://github.com/lxyeternal/pypi_malregistry) and the [Datadog collection](https://github.com/DataDog/malicious-software-packages-dataset), with revisions and per-input identities in the access index. The manuscript supplies the associated research citations.

## 8. Licence, maintenance and contributions

Author-owned PSHGuard software and associated documentation use the **MIT License**; see [LICENSE](LICENSE), [licence scope](docs/LICENSE_SCOPE.md) and [third-party notices](docs/THIRD_PARTY_NOTICES.md). Third-party package contents, inherited annotations, data/result artifacts, dependencies and model files retain their applicable terms. The separately published model archive states MIT for HGT and Apache-2.0 for ModernBERT fine-tunes. The author-code grant does not relicense the third-party input packages.

For usage questions or a failed original-input reference, [open an issue](https://github.com/snachi9895/PSHGuard-PeerJCS/issues) or contact **Junwei Zhao** at `snachi9895@gmail.com`, including the sample ID, expected SHA256, command and observed error. Proposed code or documentation improvements should be submitted in a separate branch or pull request. Changes to labels, splits, saved results or published snapshots require an explicit research/version update; they should not be mixed into a documentation correction.
