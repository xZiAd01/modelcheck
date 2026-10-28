# ModelCheck

Standalone local capstone. Preserve original course files in the parent folder.

- All metrics come from deterministic tools. Keep population and missing-data warnings attached.
- Never put credentials, uploaded data or session tokens in submission artifacts.
- Never weaken approval/path guards to improve an eval score.
- Run `uv run pytest` after behavior changes; `uv run modelcheck eval --config A B` needs an API key.
- Synthetic demonstrations are not evidence of a historical model's performance.

