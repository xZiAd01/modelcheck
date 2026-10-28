# Implementation and verification

| Component | Source and evidence | Behavior |
|---|---|---|
| Analysis | `data.py`, hand-count and scikit-learn tests | Validated joins, coverage, confusion counts and undefined denominators |
| Agent and MCP | `agent.py`, `legacy_v1.py`, `bridge.py`, `mcp_server.py`, live traces | Model-selected investigations through a stdio MCP client and server |
| Context | `review-experiment/SKILL.md`, protocol loader, compaction events | V2 host preload and protocol hash, bounded context and evidence references; v1 remains frozen |
| Approval | `store.py`, `app.py`, saved-file tests | Session-scoped decisions, exact digest, expiry and idempotent execution |
| Interface | Static HTML/CSS/JS, screenshots | Samples, uploads, live and recorded reviews, evidence and approval controls |
| Evaluation | `tasks.jsonl`, `A.csv`, `B.csv`, traces | V1: six paired tasks executed, one failure and 24 pending; v2: 36 pending; isolated smoke and targeted runs |
| Security | `SECURITY.md`, `security/live-attack.json`, handler tests | One observed v1 live attack and separately tested action controls |

Source paths are relative to `src/modelcheck/` unless they refer to files in this directory or `tests/`.
