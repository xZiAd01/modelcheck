---
name: review-experiment
description: Review binary-classification experiment exports for comparable populations, measured errors and evidence-backed follow-up experiments.
---

# Review an experiment

Inspect the manifest and validation findings before interpreting a run. Quarantined
bundles can be inspected but cannot produce trustworthy metrics.

Compare only complete, matching test populations. For partial predictions, say
which examples were measured and show coverage. Check source slices before treating
an aggregate change as uniform improvement. Distinguish a numerical decomposition
from an explanation of its cause.

Use compute_metrics, compare_runs and inspect_error_slice to establish claims.
Cite their evidence IDs. Explicit ID/group/hash overlap establishes overlap in the
supplied manifests; it does not certify a whole training pipeline. Missing
preprocessing or threshold provenance is not assessable from prediction files.

Propose one follow-up change, selected on validation data. Preserve a held-out test
set for the final assessment. Request save_experiment_spec only when the user asks
for a proposal/save; the tool queues an exact specification for human approval.
Do not claim it was saved until the approval handler confirms execution.
