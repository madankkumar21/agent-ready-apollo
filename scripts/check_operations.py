"""CI check: every operation the agent can call must be valid against the
composed supergraph. A renamed or removed field fails the build and names the
operation, before the change reaches the router.

The Apollo MCP Server does not validate operation files against the schema
when it loads them, so without this check a breaking change shows up only
when the agent calls the tool.

Usage: uv run python scripts/check_operations.py <supergraph.graphql> <operations dir>
"""

import sys
from pathlib import Path

from graphql import build_schema, parse, validate


def main(supergraph: str, ops_dir: str) -> int:
    schema = build_schema(Path(supergraph).read_text())
    failures = 0
    for op in sorted(Path(ops_dir).glob("*.graphql")):
        errors = validate(schema, parse(op.read_text()))
        for e in errors:
            failures += 1
            print(f"FAIL {op.name}: {e.message}")
        if not errors:
            print(f"ok   {op.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
