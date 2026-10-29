# Learnings: giving an agent access to your APIs

Advice for a team that wants an AI agent to read and act on data behind its existing REST APIs. Every number comes from this repo's run; see [COMPARISON.md](../COMPARISON.md).

## 1. For one agent and one task, a hand-built tool is enough

A purpose-built MCP server (Path A′) returned 848 characters to the model for the task, and the graph (Path B) returned 860. Both kept the PII out and gave the agent no tool that writes a budget. If you have one agent, one task and one team, write the tool by hand.

The plain approach of one tool per REST endpoint (Path A) is the one to avoid. The agent needed 10 calls instead of 3, the model received 11,380 characters, and four PII values reached it. The agent also made an unapproved budget write, because `set_budget` was a tool.

## 2. Use the graph when many clients need the same rules

In Path A′ the rules live in one server's Python, for one agent. A second agent, or a second server for the same agent, needs its own copy of every join, field filter and write check. In Path B those rules live in the schema. The router enforces them for every client, including one that skips the MCP server and calls the graph directly with the agent's token. That direct call got the contact fields back as `null`, and its attempt to apply a budget move never reached the ads service.

## 3. Limit the agent in two places

- **The MCP server:** list the agent's operations as files, and turn off introspection and `execute`. The agent can then run only what you reviewed. A call to any other tool is refused.
- **The router:** put field rules in the schema (`@requiresScopes`), and give the agent a token with only the scopes it needs. This holds even when the MCP server is bypassed.

Operation files limit the MCP server, not the router. A persisted query list, where operations are registered in advance and the router rejects the rest, adds that router-side limit. This repo does not use one.

## 4. Split tools by risk, not by topic

`ProposeBudgetMove` records a proposal and moves nothing. `applyBudgetMove` moves money and needs a scope only a person has. Keep them as two operations, so the agent can be given the safe one alone.

## 5. Check the agent's operations in CI

The Apollo MCP Server loads an operation file without checking it against the schema. A renamed field then shows up only when the agent calls the tool. In this repo a rename still composed cleanly; the operation check failed and named the broken operation before deploy. Put that check next to your schema build.

## 6. Keep a fast way to switch one capability off

Deleting an operation file removed the tool from the running MCP server in about 2 seconds, with no restart. To stop an agent everywhere, revoke its token or its scopes at your identity provider.

## 7. Setting up GraphOS

- JWT authentication and authorization directives are licensed router features. Without GraphOS credentials, the router refuses to start with a schema that uses `@requiresScopes`. The Free plan is enough, with a cap of 60 router requests a minute.
- The router needs the graph's key, which starts with `service:`. A personal `user:` key fails, and the Free plan cannot create variant keys. `rover init` prints a graph key once, when it creates the graph.
