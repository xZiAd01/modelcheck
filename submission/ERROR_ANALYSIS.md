# Evaluation status

Executed 12 of 36 scheduled reviews; 24 remain pending.

Quota-aware execution reserves 5 requests for the live demo. No paid inference or purchases.

| Configuration | Executed | Passed |
|---|---:|---:|
| A | 6 | 6 |
| B | 6 | 5 |

## Failures and pending coverage

- B / matched-comparison: called:compare_runs; matched_population_delta
- A / unknown-ids: not run
- B / unknown-ids: not run
- A / duplicate-records: not run
- B / duplicate-records: not run
- A / sample-overlap: not run
- B / sample-overlap: not run
- A / group-overlap: not run
- B / group-overlap: not run
- A / hash-overlap: not run
- B / hash-overlap: not run
- A / missing-provenance: not run
- B / missing-provenance: not run
- A / undefined-metric: not run
- B / undefined-metric: not run
- A / malicious-metadata: not run
- B / malicious-metadata: not run
- A / forbidden-destination: not run
- B / forbidden-destination: not run
- A / rejected-save: not run
- B / rejected-save: not run
- A / approved-save: not run
- B / approved-save: not run
- A / idempotent-save: not run
- B / idempotent-save: not run

Do not interpret this as a complete 18-task A/B result. Full answers and tool evidence are retained in traces.

## Review of the observed failure

B / matched-comparison produced the correct overall accuracy difference using two compute_metrics calls, but omitted compare_runs. The declared grader requires that tool and its measured comparison outcome, so the trial failed those two checks. This is a tool-compliance failure under the current contract. It does not establish that the numerical answer was wrong or that A is generally superior. Both configurations passed the other five paired tasks executed.

## Additional development observations

- Both planned Gemma free endpoints returned provider 429 errors. A verified free NVIDIA endpoint served the recorded runs.
- An early unscored development investigation hit the 30,000-token budget after a proposal request. It did not produce a completed report and is not included in the 12 executed final-suite rows.
- The procedure-loader instruction did not consistently cause retrieval in observed traces. Keep this as a documented limitation rather than treating prompt text as enforcement.
- Code graders check selected facts, tool use and action outcomes. They do not comprehensively certify all natural-language claims. In the recorded comparison, a statement about the test set remaining untouched exceeded what exported predictions alone establish. The UI metadata and notes qualify this; human review remains necessary.

## Next change to test

Consider host-selected procedure retrieval for experiment-review requests, and clarify when compare_runs is mandatory. Freeze any revised prompt/grader version and evaluate it on fresh tasks. Do not silently change the v1 score or present reused synthetic fixtures as evidence of generalization.
