# agent-ready-apollo

One agent task, three ways to give the agent API access, measured. Path B is [Apollo](https://www.apollographql.com): Connectors over existing REST APIs, the GraphOS Router enforcing scopes, and the Apollo MCP Server exposing a fixed set of operations as tools. Path A is a plain REST-to-MCP server with one tool per endpoint. Path A′ is the same idea written by hand for this one task.

**Why this exists.** At an AI company I built a 30-tool MCP server directly over our platform's REST APIs. The safety rules lived in my tool code: each person's token carried their org, tools read by default, nothing could delete, and ingest checked its payload first. Apollo's pitch for agents is that the graph should own rules like these instead of each tool server. I wanted to test that claim the way a customer would: same task, same data, measured on each path.

**The task.** A marketing-ops agent looks at campaign "Acme Q4", finds the line items with the worst and best cost per conversion, proposes moving $5,000, and names the account owner to notify. A human applies the move. The data is synthetic, served by three small mock REST services: `media` (contextual segments), `ads` (campaigns, line items, proposals, budgets) and `crm` (advertisers, with contact PII).

## What I tested

A scripted agent makes the same calls a model would, so every number reproduces without a model. All three paths reach the same decision, and all nine checked behavioural claims pass. Full table, the router's raw responses and the claim checks: [COMPARISON.md](COMPARISON.md).

| # | What a customer needs | Apollo (Path B) | Plain (A) / hand-built (A′) |
|---|---|---|---|
| 1 | GraphQL over existing REST, with no new service | The graph joins three REST services through Connectors; each operation touches two. 3 MCP calls; 11 REST calls behind them | A: 10 MCP calls. A′: 3, with the join hand-written |
| 2 | The agent sees only the fields it needs | 860 characters (~215 tokens) returned for the whole task | A: 11,380 (~2,845). A′: 848 |
| 3 | The agent runs only approved operations | 3 tools from operation files; a call to an unlisted `execute` tool is refused | A: 7 tools, one per endpoint |
| 4 | PII stays out of the model | 0 PII values reached the model. Called directly with the agent's token, the router returns the contact fields as `null` with `UNAUTHORIZED_FIELD_OR_TYPE`; the human's token gets them | A: 4 values. A′: 0, filtered in its code |
| 5 | Writes need a human | No apply tool. Called directly with the agent's token, `applyBudgetMove` returns `data: null` with `UNAUTHORIZED_FIELD_OR_TYPE`, and the ads service never receives the call; the human's token applies it | A: the agent's `set_budget` call succeeded |
| 6 | A schema change doesn't break the agent silently | A renamed field still composes; the CI check fails and names `CampaignPerformance` | n/a |
| 7 | Switch off one capability now | Deleting `ProposeBudgetMove.graphql` removed the tool from the running server within about 3 s; restoring it brought it back within about 3 s (2.0–3.1 s across two runs) | Edit and redeploy the server |

Token figures are estimates (characters ÷ 4, the same estimate the Apollo MCP Server prints for its own tools).

What I took from it, as advice I would give a customer:
- **For one agent and one task, a hand-built tool gets the same result.** A′ matches B on calls, characters and PII. Choose the graph when several agents or apps need the same data. The joins and field rules then live in one schema, and the router enforces them for every client.
- **Limit the agent in two places.** Operation files limit what the agent's MCP server will run. Field scopes limit what the agent's token can read anywhere, including a direct call to the router. A persisted query list adds a router-side limit on which operations run; it is not used here.
- **Split tools by risk, not by topic.** Propose and apply are separate operations with separate scopes, so the agent can be given the safe one alone.
- **Check the agent's operations in CI.** The MCP server loads an operation file without checking it against the schema, so a renamed field otherwise shows up only when the agent calls the tool.

Apollo announced [GraphOS Agent Services](https://www.apollographql.com/newsroom/press-releases/apollo-graphql-introduces-graphos-agent-services) in preview on 2026-10-07. This repo uses only generally available pieces.

## How it fits together

The diagram, a step-by-step walkthrough of one request, the design decisions, the production path and where GraphQL is the wrong tool are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Who decided what, and what broke while building it: [docs/LEDGER.md](docs/LEDGER.md). What I would tell a team giving agents API access: [docs/LEARNINGS.md](docs/LEARNINGS.md).

## Layout

```
services/      three mock REST services (FastAPI) with synthetic data; each counts its own calls
graph/         ads.graphql, media.graphql, crm.graphql: Connectors and @requiresScopes
supergraph.yaml
router/        router.yaml: JWT authentication, authorization directives
auth/          tokens.py: local RSA key, JWKS, an agent token and a human token
mcp/           config.yaml and operations/: the agent's only three tools
baseline/      rest_mcp.py (Path A) and purpose_mcp.py (Path A′)
agent/         harness.py: runs the task on all three paths and the router checks
scripts/       up.sh, ci.sh, check_operations.py, break_field.sh, report.py
.github/       CI: compose, check operations, tests, the rename self-test
```

## Run it

Before you start: [uv](https://docs.astral.sh/uv/), Rover 1.0.1 (`brew install rover`), and a free [GraphOS](https://studio.apollographql.com/signup) account. JWT authentication and `@requiresScopes` are licensed router features, so the router needs `APOLLO_KEY` and `APOLLO_GRAPH_REF` in a `.env` file at the repo root. Use the graph key (it starts with `service:`); `rover init` prints one when it creates a graph. A personal `user:` key fails with `AUTHENTICATION_FAILED`. The Free plan caps the router at 60 requests a minute; one harness run makes about ten.

```bash
uv sync
scripts/ci.sh                          # compose, check operations, tests; no key needed
scripts/run_all.sh                     # starts everything, runs all scenarios, writes COMPARISON.md, stops (needs .env)
```

Measured on: Rover 1.0.1, GraphOS Router 2.18.0, Apollo MCP Server 2.1.0, Federation 2.11, Connectors spec v0.2, MCP Python SDK 2.3.0.
