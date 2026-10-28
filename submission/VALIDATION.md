# Validation status

| Area | Evidence | Status |
|---|---|---|
| Automated contracts | 56 pytest checks | Passed |
| Locked setup | Fresh-copy uv installation and tests | See REPRODUCIBILITY.json |
| V1 live A/B | 12 of 36 reviews | A 6/6, B 5/6; 24 pending |
| V2 live A/B | 0 of 36 reviews | Pending until v1 finishes |
| Protocol availability | Controlled-provider tests | Preload, hash, failure before inference and compaction verified |
| Browser workflow | Local UI and controlled v2 provider adapter | Samples, uploads, version labels, host event, approvals and downloads checked |
| Accessibility | Keyboard, DOM accessibility tree, contrast and reflow checks | Screen-reader speech remains unverified |
| Security | One original v1 live injection fixture and handler tests | Broader live evaluation pending |

The current application runs v2. Recorded replay and published live scores belong to v1. Controlled-provider tests use deterministic responses and are separate from live evaluations.

The quota check returned five remaining requests out of 50. V1 resumption stopped before inference because 13 requests are required to preserve the demo reserve. V2's suite remains gated on v1 completion. No inference credits were purchased and no paid model was enabled.

Further validation includes the pending live suites, repeated fresh trials, broader injection cases, real exports with traceable provenance and screen-reader speech. Native browser zoom, Windows forced-colors rendering and physical mobile-device behavior are unverified. The text-size stress test uses 200% root text sizing rather than native browser zoom.
