# Implementation and verification

| Component | Source and evidence | Behavior |
|---|---|---|
| Analysis | `data.py`, hand-count and scikit-learn tests | Validated joins, coverage, confusion counts and undefined denominators |
| Agent and MCP | `agent.py`, `bridge.py`, `mcp_server.py`, live traces | Model-selected investigations through a stdio MCP client and server |
| Context | `review-experiment/SKILL.md`, protocol loader, compaction events | Procedure retrieval, bounded context and evidence references; inconsistent loader invocation in observed traces |
| Approval | `store.py`, `app.py`, saved-file tests | Session-scoped decisions, exact digest, expiry and idempotent execution |
| Interface | Static HTML/CSS/JS, screenshots | Samples, uploads, live and recorded reviews, evidence and approval controls |
| Evaluation | `tasks.jsonl`, `A.csv`, `B.csv`, traces | Six paired tasks executed; one tool-compliance failure and 24 pending reviews |
| Security | `SECURITY.md`, `security/live-attack.json`, handler tests | One observed live attack and separately tested action controls |

Source paths are relative to `src/modelcheck/` unless they refer to files in this directory or `tests/`.
