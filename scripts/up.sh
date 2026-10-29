#!/usr/bin/env bash
# Start the demo: three mock REST services, the router (via rover dev) and the
# Apollo MCP Server. Versions are pinned to what the results were measured on.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Missing .env with APOLLO_KEY and APOLLO_GRAPH_REF. See README, 'Before you start'."; exit 1; }
set -a; source .env; set +a
[ -f auth/agent.jwt ] || uv run python -m auth.tokens
mkdir -p logs
export JWKS_URL="file://$PWD/auth/jwks.json"
export AGENT_TOKEN="$(cat auth/agent.jwt)"
export APOLLO_ELV2_LICENSE=accept APOLLO_ROVER_ALLOW_AUTOMATIC_DOWNLOAD=true
uv run python -m services.run > logs/services.log 2>&1 &
echo "services: media :4101, ads :4102, crm :4103 (pid $!)"
exec rover dev \
  --supergraph-config supergraph.yaml \
  --router-config router/router.yaml \
  --router-version 2.18.0 \
  --supergraph-port 4000 \
  --mcp mcp/config.yaml \
  --mcp-version 2.1.0
