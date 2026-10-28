# V1 evaluation analysis

Executed 12 of 36 scheduled reviews; 24 remain pending.

Quota-aware execution reserves five requests for the live demo.

The latest resumption found zero requests remaining and stopped before inference. All 12 original outcomes and traces remain unchanged. V2 remained gated on v1 completion; no new live outcome is available from this session. See QUOTA_STATUS.json for the timestamped allowance check.

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
- V1 procedure-loader instructions did not consistently cause retrieval in observed traces. The frozen v1 engine retains that behavior; v2 supplies the protocol from the host before inference.
- Code graders check selected facts, tool use and action outcomes. They do not comprehensively certify all natural-language claims. In the recorded comparison, a statement about the test set remaining untouched exceeded what exported predictions alone establish. The interface flags this unsupported provenance claim alongside the original report.

## V2 implementation and pending evidence

V2 loads the packaged protocol before the first provider request, records its version and SHA-256 and preserves it during compaction. Failure to load a valid protocol stops the review before inference. Comparison instructions explicitly require compare_runs for comparison conclusions. These changes guarantee protocol availability, while model adherence and live task outcomes still require measurement.

The 56 automated tests cover the protocol, permissions and evaluator changes. Controlled-provider browser testing verified the host event, version labels, approval and downloaded JSON without using OpenRouter inference.

V2 has zero executed live reviews and 36 pending. Its live evaluation is gated on completion of the v1 full suite. No measured improvement or v2 live pass rate is established. New runtime fingerprints use a separate directory, and targeted reruns retain their own scores.

## Evidence preservation

The initial snapshot contains unchanged v1 source, tasks, traces and reports with checksums. The original 12 executions are labeled as imported evidence; configuration metadata was recovered from the published source. V1's pending reviews use the byte-identical legacy reviewer and unchanged fixtures, graders, protocol and dependencies. New traces capture runtime fingerprints and execution provenance directly.

Generated coverage belongs in COVERAGE.md. The evaluator does not overwrite this narrative. Missing keys and quota stops retain executed rows. Atomic checkpoints and trace checksums support recovery after an interrupted write without repeating a completed provider investigation.
