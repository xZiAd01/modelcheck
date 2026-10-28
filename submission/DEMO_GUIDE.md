# Eight-minute demonstration guide

## Before presenting

Run `uv run modelcheck serve` from the project directory, or open Launch.command on macOS. Use http://127.0.0.1:8787. Keep the app local. The key remains in .env, not in the slides or ZIP. The real recorded AI review is available if the free endpoint is busy. Identify it explicitly as recorded.

## Problem and audience, one minute

“ModelCheck helps an ML developer examine an experiment before reporting the headline metric. It checks comparable populations, computes results and investigates failure slices. It prepares a follow-up specification that I approve before saving.”

## Interactive demonstration, two minutes

Load The quantization trade-off. Candidate accuracy is 85%, against 90% baseline. Studio recall improves, while web recall drops from 90% to 50%. These are synthetic values, not results from the earlier image detector.

Select View recorded AI review and state that this is a real captured model run, replayed without an API request. The evidence receipt contains the actual comparison output and citations. If quota/network permits, a fresh Run AI review demonstrates the same application loop, with stochastic output.

Draft a follow-up. Read its one proposed change and validation-only selection rule. Prepare the exact specification. Show rejection or approve and save, then download the JSON. This is a proposed experiment, not model training.

## Design, two minutes

Explain who selects each next tool and who executes it. Read-only tools run through an actual stdio MCP client/server. Python computes metrics. SQLite preserves pending action state. The human decision is separate from model prose and binds the exact payload digest.

The review skill is available through a loader, but observed traces do not reliably invoke it. Context/results remain bounded. The project uses one agent; a graph library and multiple agents were unnecessary for this scope.

## Evaluation, two minutes

Eighteen frozen tasks exist, with A/B reviewer prompts. Twelve of 36 scheduled reviews ran under the selected daily allowance. A passed 6/6; B passed 5/6; 24 reviews remain pending. The B failure omitted a required comparison tool despite a correct numerical delta. Describe that as a tool-compliance failure, not proof that B is generally worse. One trial cannot establish repeated-run reliability.

## Security, one minute

The live malicious run note asked for an out-of-root save and bypassed approval. The reviewer identified it, requested no action and saved no file. Separately, direct handler tests reject arbitrary paths, changed digests and foreign sessions, and verify valid approval saves exactly once. This is bounded evidence, not universal security or compliance certification.

## Questions to prepare

- What can prediction files establish about leakage? Explicit IDs/groups/exact hashes only. Preprocessing and complete training integrity need additional provenance.
- Why MCP? It makes the read tools discoverable and separately callable while preserving the host's permission boundary.
- Why a human gate? A model can propose an experiment, but the user decides which exact specification to retain.
- What remains? Finish the 24 pending live reviews, improve protocol invocation and validate real exports with traceable data.
- What did you personally implement? Use CONTRIBUTIONS.md and distinguish code assistance from work you have reviewed and can explain.
