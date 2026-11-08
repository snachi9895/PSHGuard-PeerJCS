# PeerJ manuscript-to-file index

The scientific results reuse the frozen PSHGuard experiments. The figure numbering below follows the PeerJ draft.

| Paper item | Files | Identity |
| --- | --- | --- |
| Figure 1, framework | Method implementation in scripts/; no numerical figure-source table | Author-prepared system illustration. |
| Figure 2, static cases | Original package identity metadata in data/manifests/ and access references in data/access/; original archives remain external | Author-prepared static examples, no package execution. Artwork and raw sample source are not bundled here. |
| Figure 3, branch comparison | figure_source/v3/data/branch_comparison.csv; data/predictions/final_test/; data/statistics/final_test/ | Absolute F1 and matched paired seed/component intervals. |
| Figure 4, ablation and file budgets | figure_source/v3/data/single_hgt.csv, fusion_reference.json, fusion_ablation_ci.csv, dual_branch_budgets.csv; results/graph_representation/; data/predictions/file_budget/ | Single HGT and same-seed fusion are different objects. SD and CI are kept separate. |
| Figure 5, prepared-input efficiency | figure_source/v3/data/efficiency.csv; saved S9-E1 results in results/historical_20260911/ | Prepared-input branch measurements; serial fusion timing is an estimate. |
| Figure 6, perturbations and observed strata | figure_source/v3/data/perturbations_and_strata.csv; saved S9-F/S9-H results | Frozen perturbations and unmatched observational strata. |
| Figure 7, size strata | figure_source/v3/data/size_strata.csv; data/predictions/validation/source_size_joined.csv | Fixed size-only LR versus three-run PSHGuard, same validation population. |
| Table 1, external detectors | results/current/table_01_existing_detectors.csv; results/current/pypimaldet_r4_saved_summary.json | Seven external comparators plus PSHGuard. |
| Table 2, representation ablation | results/current/table_02_graph_representation.csv; results/graph_representation/ | Raw AP and OOF classification, three-run mean/sample SD. |
| Table 3, joint-size diagnosis | results/current/table_03_common_support.csv, table_03_auroc_and_fpr.csv; results/source_size/; data/statistics/source_size/ | Raw, retained and weighted populations; Datadog weighted CIs remain missing under the valid-draw rule. |
| Component split | data/manifests/; results/split_audit/; scripts/final_source_clone_split_20260611/ | 20,878 samples and 11,813 components; >50-package components are training-only. |
| Calibration and low prevalence | results/current/applicability_saved_values.json, low_prevalence_saved_projection.csv; saved S9-H files | ECE belongs to validation OOF; low-prevalence numbers are conditional projections. |
| Partial source holdout | Saved S9-G2 files under results/historical_20260911/ | List/prefix-defined partial shift, not an independent temporal test. |

The original historical aggregates are retained for provenance. Some describe a three-HGT auxiliary ensemble rather than the final single-HGT branch. Use the current indices and the labelled figure-source files when reading them.

Additional diagnostic and comparator inputs are in data/supplementary/saved_outputs_v1.zip. metadata/SUPPLEMENTARY_OUTPUT_INDEX.csv assigns each member to its paper item. See docs/SAVED_OUTPUTS.md for population and historical-system distinctions.
