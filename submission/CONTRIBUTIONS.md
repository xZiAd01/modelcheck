# Contribution and evidence map

This project was built in collaboration with Codex. Zeyad selected the problem and scope; implementation ownership and understanding should be established through review and demonstration rather than inferred from generated code.

| Area | Evidence to inspect | What to explain in the presentation |
|---|---|---|
| Deterministic analysis | data.py, hand-count and scikit-learn tests | Join grain, coverage, confusion counts and undefined denominators |
| Agent and MCP | agent.py, bridge.py, mcp_server.py, live traces | Model chooses tools; host executes through a real stdio client |
| Context | review-experiment/SKILL.md, loader and compaction events | Available procedure retrieval and its observed model-following limitation |
| Approvals | store.py, app.py, saved-file tests | Exact digest, session scope, expiry and idempotent execution |
| UI | static files, screenshots | Samples, upload contract, recorded versus live, evidence and human decision |
| Evaluation | tasks.jsonl, A.csv, B.csv, traces | Partial coverage, one tool-compliance regression, unexecuted cases |
| Security | SECURITY.md and live-attack.json | Model behavior differs from code-enforced action controls |

Before presenting, Zeyad should trace one request through the code, change one fixture and predict its metrics, demonstrate rejection and approval, and explain why 24 pending trials cannot support a full-suite score.
