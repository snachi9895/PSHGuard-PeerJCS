# Saved prediction and statistics files

All prediction/statistics files were copied from saved experiment outputs without recomputing scores or metrics. metadata/SOURCE_COPY_MAP.csv maps each destination to its source and hash.

- data/predictions/final_test/: graph, ModernBERT and fusion decisions for seeds 1001-1003, plus EA4MP for seeds 42-44. Every file contains 2,128 rows with sample_id, y_true, score and prediction.
- data/predictions/validation/same_seed_oof_predictions.csv: 2,137 rows, original component and fold identifiers, with each seed's graph, sequence and same-seed fusion output. Historical three-HGT reference columns remain labelled as references.
- data/predictions/validation/source_size_joined.csv: 2,137 rows with the fixed LR score, source/list and retrieval-channel fields, file-count/byte attributes, component/fold fields and neural branch outputs. The original graph-file count and fingerprint count are different recorded definitions.
- data/predictions/file_budget/: four 2,137-row tables, graph-file limits 4, 8, 16 and 32. They retain raw branch margins, OOF fusion scores/decisions and fold thresholds.
- configs/frozen_deployment_fits.json: saved deployment fit parameters, fitted on validation and then frozen for final test.
- data/statistics/final_test/: corrected official saved table, identity audit, results, paired statistics and paired-bootstrap output. The reporting overlay retains the exact-V2 denominator.
- data/statistics/validation/: original saved S8 component/hierarchical seed-component bootstrap outputs.
- data/statistics/source_size/: saved bootstrap array and its explicit axes. Retain the missing Datadog weighted intervals and validity rule.

Scores and predictions are saved evaluation outputs, not new labels or deployment-probability guarantees. Join package-level fields by sample_id to data/manifests/. Additional external-detector and diagnostic input coverage must be audited before claiming that every result can be recomputed from this package alone.
