# Implementation and evidence map

This map connects each application component to its implementation and verification evidence.

| Area | Evidence to inspect | What to explain in the presentation |
|---|---|---|
| Deterministic analysis | data.py, hand-count and scikit-learn tests | Join grain, coverage, confusion counts and undefined denominators |
| Agent and MCP | agent.py, bridge.py, mcp_server.py, live traces | Model chooses tools; host executes through a real stdio client |
| Context | review-experiment/SKILL.md, loader and compaction events | Available procedure retrieval and its observed model-following limitation |
| Approvals | store.py, app.py, saved-file tests | Exact digest, session scope, expiry and idempotent execution |
| UI | static files, screenshots | Samples, upload contract, recorded versus live, evidence and human decision |
| Evaluation | tasks.jsonl, A.csv, B.csv, traces | Partial coverage, one tool-compliance regression, unexecuted cases |
| Security | SECURITY.md and live-attack.json | Model behavior differs from code-enforced action controls |

