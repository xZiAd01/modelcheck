# Demo walkthrough

The eight-minute walkthrough covers the review workflow, architecture, evaluation and security evidence.

## Setup

From the project directory, run `uv run modelcheck serve`, or open `Launch.command` on macOS. The interface is at <http://127.0.0.1:8787>. Live review uses the key in `.env`; recorded review is available without a provider request and is labeled in the interface.

## Problem · one minute

Headline metrics can hide source-specific failures, incomplete coverage and missing provenance. ModelCheck checks the population, calculates metrics, investigates error slices and prepares an experiment specification for approval.

## Review workflow · two minutes

1. Load **The quantization trade-off**. Candidate accuracy is 85%, against a 90% baseline. Studio recall improves from 90% to 100%; web recall falls from 90% to 50%. The fixture is synthetic.
2. Open **View recorded AI review**. This replays a captured v1 inference; the evidence receipt includes comparison output and citations. **Run AI review** starts a fresh v2 investigation when quota and network access permit.
3. Select **Draft a follow-up**. The proposal contains one change, a validation-only selection rule and a success criterion.
4. Review the exact specification, then reject or approve and save. Rejection creates no file. Approval creates one downloadable JSON specification. The application does not train a model.

## Architecture · two minutes

A single agent selects investigation tools. Four read-only tools run through a stdio MCP client and server. Python computes the metrics. SQLite stores evidence and pending actions. A separate approval handler binds the decision to the exact payload digest and session.

The v2 host loads and fingerprints the review protocol before inference and preserves it during compaction. The original v1 reviewer remains frozen for evaluation resumption. Context and tool results remain bounded. Model inference runs externally through OpenRouter.

## Evaluation · two minutes

The frozen v1 suite contains 18 tasks and two reviewer configurations. Twelve of 36 scheduled reviews ran under the daily request limit: A passed 6/6 and B passed 5/6, with 24 reviews pending.

V2 has 36 scheduled reviews and no live results yet. Its live evaluation starts after v1 finishes. The 56 automated tests and controlled-provider browser checks are separate evidence.

V1 B omitted the required comparison tool in one case despite returning the correct numerical delta. The failure concerns the declared tool contract. The partial suite and one trial per task are insufficient to compare general reliability.

## Security · one minute

The v1 malicious run description requested an out-of-root save and an approval bypass. The live reviewer identified it and created no action or file. Separate handler tests reject arbitrary paths, changed digests and foreign sessions. Valid approval tests verify exact JSON contents and one saved file after repeated approval.

The evidence covers one live attack and the tested handler cases. Broader live security evaluation remains pending.

## Technical reference

| Topic | Supported behavior |
|---|---|
| Leakage inspection | Explicit sample, group and exact-hash overlap in supplied manifests; training and preprocessing integrity require additional provenance |
| MCP | Discoverable read tools called through a separate client/server connection |
| Human approval | A decision on the exact proposed specification before a file is saved |
| Remaining validation | Remaining v1 and v2 live reviews, repeated trials and real exports with traceable provenance |
