# Evaluation status

Executed 12 of 36 scheduled reviews; 24 remain pending.

Quota-aware execution reserves five requests for the live demo.

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

Coverage is partial across the 18-task A/B suite. Full answers and tool evidence are retained in traces.

## Review of the observed failure

B / matched-comparison produced the correct overall accuracy difference using two compute_metrics calls, but omitted compare_runs. The declared grader requires that tool and its measured comparison outcome, so the trial failed those two checks. This is a tool-compliance failure under the current contract. It does not establish that the numerical answer was wrong or that A is generally superior. Both configurations passed the other five paired tasks executed.

## Additional development observations

- Both planned Gemma free endpoints returned provider 429 errors. A verified free NVIDIA endpoint served the recorded runs.
- An early unscored development investigation hit the 30,000-token budget after a proposal request. It did not produce a completed report and is not included in the 12 executed final-suite rows.
- The procedure-loader instruction did not consistently cause retrieval in observed traces. Procedure retrieval is prompted rather than enforced by the host.
- Code graders check selected facts, tool use and action outcomes. They do not comprehensively certify all natural-language claims. In the recorded comparison, a statement about the test set remaining untouched exceeded what exported predictions alone establish. The interface flags this unsupported provenance claim alongside the original report.

## Proposed evaluation revision

A future revision could retrieve the procedure at the host level and make the compare_runs requirement explicit. Revised prompts or graders require a new version and fresh evaluation; the current v1 results remain the baseline. Reused synthetic fixtures provide regression coverage, with generalization requiring additional data.
