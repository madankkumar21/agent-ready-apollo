#!/usr/bin/env bash
# What CI runs, and what you can run locally. No GraphOS key needed:
# composing a supergraph needs only the ELv2 licence acceptance.
set -euo pipefail
cd "$(dirname "$0")/.."
export APOLLO_ELV2_LICENSE=accept
out=$(mktemp -d)
echo "== compose the supergraph"
rover supergraph compose --config supergraph.yaml > "$out/supergraph.graphql"
echo "== check every MCP operation against it"
uv run python scripts/check_operations.py "$out/supergraph.graphql" mcp/operations
echo "== unit tests"
uv run pytest -q
echo "== self-test: a renamed field must fail the operation check"
scripts/break_field.sh
