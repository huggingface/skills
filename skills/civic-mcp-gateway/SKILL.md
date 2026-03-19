---
name: civic-mcp-gateway
description: "Connect AI agents to 85+ tools (Gmail, Google Calendar, PostgreSQL, Slack, and more) through Civic's MCP Gateway with guardrails, scoped permissions, audit trails, and revocable access. Civic separates the permission layer from the AI agent so they can't get around restrictions."
---

# Civic MCP Gateway

Connect to Civic's MCP Gateway for identity, authorization, audit trails, and revocable access when calling MCP tools.

## MCP Server Configuration

```json
{
  "mcpServers": {
    "civic": {
      "url": "https://app.civic.com/hub/mcp"
    }
  }
}
```

**Claude Code:**
```bash
claude mcp add --transport http civic https://app.civic.com/hub/mcp
```

## Setup

1. Sign up at https://app.civic.com and generate a bearer token
2. Configure the MCP server above in your agent's settings
3. On first connection, complete the OAuth flow in your browser

## What it does

- **85+ MCP servers** — Gmail, Google Calendar, PostgreSQL, Slack, and more available through a single gateway
- **Guardrails** — block destructive operations, redact PII from responses, enforce rate limits
- **Audit trail** — every tool call logged with agent identity and timestamp
- **Scoped permissions** — grant agents access to specific tools only
- **Revocable access** — revoke a token and the agent loses access immediately

## Guardrail examples

- Block Gmail sends containing secrets or to external domains
- Enforce read-only PostgreSQL access (block DROP, DELETE, ALTER)
- Redact PII from tool responses before they enter agent context
- Prevent bulk operations and enforce rate limits

## Documentation

Full docs at https://docs.civic.com/civic/quickstart
