# Versioned evaluation evidence

| Location | Runtime and purpose |
|---|---|
| Parent submission directory | Current full v1 A/B suite and generated coverage |
| `v1/initial/` | Original source and evidence snapshot from release `20f61032851a1eaca3a23956f90ea0dd1cff8c3b` |
| `v1/<fingerprint>/` | Separate v1 subset or targeted runs |
| `v2/<fingerprint>/` | V2 suite, subset or targeted runs |
| Project `runtime/smoke/<run-id>/` | Local smoke checks, excluded from publication |

The initial snapshot mirrors the original project paths. `manifest.json` checksums the preserved source and evidence. `configuration.json` and `imports.json` identify recovered configuration and the 12 original executions. This metadata was recovered after execution; the original traces were not rewritten.

New runs record source, prompt, protocol, schema, grader, fixture and dependency fingerprints. The directory's metadata and progress define its exact selection and runtime. Mismatched configurations require a new output directory. Changes to frozen v1 behavior stop its resumption.

The full v1 suite finishes before v2 live evaluation. Completion means all 36 trials have recorded outcomes; failed trials remain failures. The gate also verifies trace checksums. Each fresh trial requires at least 13 remaining provider requests, reserving five for the demo and eight for a bounded review. Unknown quota stops evaluation without inference.

Exit codes are 0 for a complete passing run, 1 for a complete run containing failures and 2 for incomplete execution. The full v1 command resumes only pending rows. Targeted runs select explicit task IDs and retain separate scores. Smoke checks cannot overwrite submission results.

Progress is the canonical checkpoint; reports can be regenerated from it. A newly committed trace includes its outcome row. If interruption occurs before progress is replaced, resumption validates and imports that trace instead of repeating the provider call. A checksum mismatch or invalid checkpoint stops the run.

COVERAGE.md is generated. ERROR_ANALYSIS.md is maintained separately. Scores from different runtime versions, fingerprints or targeted selections are never combined into a single pass rate.
