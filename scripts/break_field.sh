#!/usr/bin/env bash
# Scenario 6: the ads team renames LineItem.conversions to conversionCount and
# updates its connector mapping. The graph still composes, so nothing in the
# graph build complains. The agent's CampaignPerformance operation still asks
# for `conversions`, so the operation check must fail and name it.
set -uo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
mkdir -p "$tmp/graph" && cp graph/*.graphql "$tmp/graph/"
sed -i.bak -e 's/^  conversions: Int$/  conversionCount: Int/' \
           -e 's/id name status budget spend impressions clicks conversions/id name status budget spend impressions clicks conversionCount: conversions/' \
           "$tmp/graph/ads.graphql"
sed "s#graph/#$tmp/graph/#" supergraph.yaml > "$tmp/supergraph.yaml"
echo "== compose the changed graph"
APOLLO_ELV2_LICENSE=accept rover supergraph compose --config "$tmp/supergraph.yaml" > "$tmp/supergraph.graphql" 2>"$tmp/compose.err" \
  && echo "composes: yes" || { echo "composes: no"; cat "$tmp/compose.err"; exit 2; }
echo "== check the agent's operations against it"
uv run python scripts/check_operations.py "$tmp/supergraph.graphql" mcp/operations
status=$?
rm -rf "$tmp"
if [ $status -ne 0 ]; then echo "RESULT: the check caught the break (exit $status)"; exit 0; else echo "RESULT: the check missed the break"; exit 1; fi
