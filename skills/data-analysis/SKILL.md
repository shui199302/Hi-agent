---
name: data-analysis
description: "Inspect and analyze tabular data with reproducible calculations, quality checks, and clear caveats. Use for CSV or TSV profiling, descriptive statistics, segment comparison, trend analysis, anomaly review, and decision-oriented interpretation of supplied datasets."
---

# Data Analysis

## Workflow

1. Define the unit of observation, target measures, time range, and decision the analysis should inform.
2. Profile schema, missingness, duplicates, types, ranges, and category cardinality before calculating conclusions.
3. Preserve the original data. Document filtering, coercion, exclusions, and denominator choices.
4. Use the simplest analysis that answers the question. Separate description, association, and causal claims.
5. Validate surprising results with an independent calculation and relevant subsets.
6. Report findings with units, sample size, uncertainty, limitations, and reproducible steps.

For CSV or TSV profiling, run `scripts/profile_csv.py` only after skill-script execution has been enabled. Pass `--root` as the approved workspace and keep the input within that root. The script never evaluates cell contents or writes to the dataset.

Read [references/analysis-contract.md](references/analysis-contract.md) before interpreting statistics or preparing the final answer.
