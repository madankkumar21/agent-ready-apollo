# Build ledger

Built with Claude Code over one evening. A second model reviewed the plan before the build. This page records who decided what, how each decision was checked, and what broke.

## Decisions

| Decision | Who decided | How it was checked |
|---|---|---|
| Domain: a marketing-ops agent that reads spend against results and proposes moving budget | Agent proposed two domains; Madan chose this one because it matches Apollo's own Agent Services pilot | Same decision on all three paths (`same_decision: true` in `results/run.json`) |
| Scope: six scenarios, plus the operation-file kill switch | Madan chose six; the kill switch came from the plan review | Each scenario has a script or a line in `results/run.json` |
| PII: contact name, email, phone and billing address need `pii:read`; the account owner's name does not | Agent proposed, Madan approved | Harness string-matches the seeded PII in everything returned to the model: 4 values on Path A, 0 on Path B |
| Writes split by risk: the agent proposes, a human applies | Agent proposed, Madan approved | `applyBudgetMove` is not an MCP tool; the agent's token is checked at the router (see COMPARISON.md) |
| The agent's tools are three operation files, with introspection and execute off | Agent | Tool list has 3 names; a call to an unlisted `execute` tool is refused by the server |
| Build Path A′, a purpose-built baseline, so the comparison is fair | Plan review recommended it; adopted | A′ returns 848 characters against B's 860 |
| Validate operations with graphql-core against the composed supergraph | Agent, after the review found that the MCP server does not validate operation files on load | `scripts/break_field.sh`: the renamed field composes and the check fails on `CampaignPerformance` |

## What broke

1. **The router would not start** when the schema used `@requiresScopes` and no GraphOS credentials were set: "license violation … Authorization directives, requiresScopes". This happened even with directive checks turned off in the router config. JWT authentication is licensed the same way. Fix: a free GraphOS account and `APOLLO_KEY` / `APOLLO_GRAPH_REF`.
2. **Composition failed**: "Non-shareable field Segment.id is resolved from multiple subgraphs". The types resolved by connectors needed an explicit `@key(fields: "id")`, and the referencing subgraph needed `resolvable: false`.
3. **The first rename test failed for the wrong reason.** Renaming `LineItem.conversions` broke composition, because the connector's mapping still named the field. A real rename updates the mapping (`conversionCount: conversions`). Then the graph composes and only the agent's operation breaks, which is the case the check exists for.
4. **The MCP Python SDK 2.x renamed its API**: `FastMCP` became `MCPServer`, `streamablehttp_client` became `streamable_http_client`, and `isError` became `is_error`.
5. **An unlisted tool raises a protocol error, not a tool error.** The Apollo MCP Server answers "Tool execute not found". The harness records that as refused.
6. **An odd warning:** without credentials, `rover dev` printed that `@connect` was disabled, but connector queries still resolved locally. The README requires the key anyway.
7. **The wrong key type.** A personal `user:` key failed at the router with `AUTHENTICATION_FAILED … did not parse to a valid key format`. The Free plan also refused to create a variant key (`NOT_ALLOWED_BY_USER_ROLE`). The working key was the graph key that `rover init` prints once, starting `service:`.

## Measured at the router, with the key

With the agent's token, `contactEmail` and `contactPhone` came back `null` with `UNAUTHORIZED_FIELD_OR_TYPE`, and `accountOwner` came back. A direct `applyBudgetMove` returned `data: null` with the same code, and the ads service log shows no `/apply` call. With the human's token, both worked. These match Apollo's description of authorization directives; the raw responses are in [COMPARISON.md](../COMPARISON.md).
