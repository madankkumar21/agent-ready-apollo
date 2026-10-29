#!/usr/bin/env bash
# One command: start the stack, run every scenario, write COMPARISON.md, stop
# everything. Exits 0 only if every expectation in results/run.json passes.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
log=logs/run_all.log

stop_all() {
  [ -f mcp/operations/ProposeBudgetMove.graphql ] || git checkout -- mcp/operations/ProposeBudgetMove.graphql 2>/dev/null
  pkill -f "services.run" 2>/dev/null
  pkill -f "rover dev" 2>/dev/null
  pkill -f "/.rover/bin/router" 2>/dev/null
  pkill -f "/.rover/bin/apollo-mcp-server" 2>/dev/null
  for _ in $(seq 1 20); do
    pgrep -f "services.run|rover dev|/.rover/bin/" >/dev/null || return 0
    sleep 0.5
  done
  echo "warning: some processes were still running after 10 s"
}
trap stop_all EXIT
stop_all; sleep 1

scripts/up.sh > "$log" 2>&1 &

echo "== waiting for the router and the MCP server"
ready=""
for _ in $(seq 1 180); do
  if grep -q -E "license violation|AUTHENTICATION_FAILED|no valid license|Router process exited|Missing .env" "$log"; then
    echo "startup failed:"; grep -E "ERROR|exited|Missing" "$log" | sed -E 's/(service:|user:)[^ "]*/\1<hidden>/g' | head -5
    exit 2
  fi
  if curl -sf http://127.0.0.1:8088/health >/dev/null 2>&1 && grep -q "Starting MCP server" "$log"; then ready=yes; break; fi
  sleep 1
done
[ -n "$ready" ] || { echo "timed out waiting for the stack; see $log"; exit 2; }
echo "ready"

echo "== running the scenarios"
uv run python -m agent.harness
status=$?
uv run python scripts/report.py
exit $status
