---
name: ai-status-monitor
description: Monitor real-time status for major AI providers, search model availability and pricing, and report trending models, benchmark rankings, and incidents from aistatus.cc. Use when users ask if a provider is down, whether a model is available, or what models are trending/high-performing.
---

# AI Status Monitor (aistatus.cc)

Use this skill to query public API endpoints from `https://aistatus.cc`.

## Endpoint map

- `GET /api/all`
  Returns a full snapshot:
  - `status`: `{ providerStatus: [...], totalModels }`
  - `trending`: `{ week, models: [...] }`
  - `mmlu`: `[ ... ]` (top benchmark models)
  - `incidents`: `[ ... ]` (recent status transitions)
  - `lastUpdated`

- `GET /api/status`
  Returns provider-level status:
  - `providerStatus[]`: `{ slug, name, modelCount, status, statusDetail, ... }`
  - `totalModels`
  - `lastUpdated`

- `GET /api/model?q=<query>`
  Returns model search results:
  - `query`, `count`, `models[]`, `lastUpdated`
  - model entries include `id`, `name`, `provider`, `context_length`, `pricing`, `modality`

- `GET /api/trending`
  Returns OpenRouter weekly usage ranking:
  - `week`
  - `models[]`: `{ rank, id, name, provider, tokens, tokensFormatted, ... }`
  - `lastUpdated`

- `GET /api/mmlu`
  Returns benchmark leaderboard:
  - `models[]`: `{ rank, name, avgScore, mmluPro, mathLvl5, gpqa, params, type }`
  - `lastUpdated`

- `GET /api/incidents`
  Returns recent provider status changes:
  - `incidents[]`: `{ slug, name, from, to, detail, timestamp }`

## Request strategy

1. Default to `GET /api/all` for broad or ambiguous requests.
2. Use `GET /api/status` for provider uptime/outage questions.
3. Use `GET /api/model?q=...` for model lookup, context length, or price checks.
4. Use `GET /api/trending` for popularity/usage ranking questions.
5. Use `GET /api/mmlu` for benchmark leaderboard questions.
6. Use `GET /api/incidents` for outage history or recent changes.

## Response rules

- Include the API timestamp field (`lastUpdated` or event `timestamp`) when available.
- For provider status, report `status`, `statusDetail` (if present), and `modelCount`.
- For model search, show top matches first and include provider status plus pricing.
- For rankings, preserve rank order and clearly label the metric (`tokens` or `avgScore`).
- If the query is vague, return a concise summary from `/api/all` and ask one follow-up question.
