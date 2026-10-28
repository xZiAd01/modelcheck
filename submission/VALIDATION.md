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

The latest quota check returned zero remaining requests out of 50; the earlier check recorded five. V1 resumption stopped before inference because 13 requests are required by the demo-reserve policy. No new evaluation inference ran during this resumption. V2's suite remains gated on v1 completion. No inference credits were purchased and no paid model was enabled. The timestamped response fields are in QUOTA_STATUS.json.

A silent browser recording in demo/ModelCheck_walkthrough.mp4 demonstrates the synthetic comparison, explicitly labeled v1 replay, manual proposal, exact approval and JSON download. It uses the current application's real approval handler and does not establish live v2 model performance. Captions and a playback page accompany the recording.

Further validation includes the pending live suites, repeated fresh trials, broader injection cases, real exports with traceable provenance and screen-reader speech. Native browser zoom, Windows forced-colors rendering and physical mobile-device behavior are unverified. The text-size stress test uses 200% root text sizing rather than native browser zoom.
