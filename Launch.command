#!/bin/zsh
cd -- "$(dirname -- "$0")"
if command -v uv >/dev/null 2>&1; then
  exec uv run modelcheck serve
elif [[ -x "$HOME/.local/bin/uv" ]]; then
  exec "$HOME/.local/bin/uv" run modelcheck serve
else
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  read -r "?Press Enter to close."
fi
