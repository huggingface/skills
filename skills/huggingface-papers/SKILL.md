---
name: huggingface-papers
description: Look up, read, search, and list Hugging Face paper pages using the `hf papers` CLI or the papers REST API. Fetch paper content as markdown, get structured metadata (authors, linked models/datasets/spaces, Github repo, project page), search papers by keyword, and browse the daily papers feed. Use when the user shares a Hugging Face paper page URL, an arXiv URL or ID, or asks to summarize, explain, analyze, search, or list AI research papers.
---

# Hugging Face Paper Pages

Hugging Face Paper pages (hf.co/papers) is a platform built on top of arXiv (arxiv.org), specifically for research papers in the field of artificial intelligence (AI) and computer science. Hugging Face users can submit their paper at hf.co/papers/submit, which features it on the Daily Papers feed (hf.co/papers). Each day, users can upvote papers and comment on papers. Each paper page allows authors to:
- claim their paper (by clicking their name on the `authors` field). This makes the paper page appear on their Hugging Face profile.
- link the associated model checkpoints, datasets and Spaces by including the HF paper or arXiv URL in the model card, dataset card or README of the Space
- link the Github repository and/or project page URLs
- link the HF organization. This also makes the paper page appear on the Hugging Face organization page.

Whenever someone mentions a HF paper or arXiv abstract/PDF URL in a model card, dataset card or README of a Space repository, the paper will be automatically indexed. Note that not all papers indexed on Hugging Face are also submitted to daily papers. The latter is more a manner of promoting a research paper. Papers can only be submitted to daily papers up until 14 days after their publication date on arXiv.

The Hugging Face team has built an easy-to-use API and CLI to interact with paper pages. Content of the papers can be fetched as markdown, or structured metadata can be returned such as author names, linked models/datasets/spaces, linked Github repo and project page.

## When to Use

- User shares a Hugging Face paper page URL (e.g. `https://huggingface.co/papers/2602.08025`)
- User shares a Hugging Face markdown paper page URL (e.g. `https://huggingface.co/papers/2602.08025.md`)
- User shares an arXiv URL (e.g. `https://arxiv.org/abs/2602.08025` or  `https://arxiv.org/pdf/2602.08025`)
- User mentions a arXiv ID (e.g. `2602.08025`)
- User asks you to summarize, explain, or analyze an AI research paper
- User asks to search, list, or browse AI research papers

## Parsing the paper ID

It's recommended to parse the paper ID (arXiv ID) from whatever the user provides:

| Input | Paper ID |
| --- | --- |
| `https://huggingface.co/papers/2602.08025` | `2602.08025` |
| `https://huggingface.co/papers/2602.08025.md` | `2602.08025` |
| `https://arxiv.org/abs/2602.08025` | `2602.08025` |
| `https://arxiv.org/pdf/2602.08025` | `2602.08025` |
| `2602.08025v1` | `2602.08025v1` |
| `2602.08025` | `2602.08025` |

This allows you to provide the paper ID into any of the CLI commands or API endpoints mentioned below.

## `hf papers` CLI (preferred)

The `hf` CLI (part of the `huggingface_hub` package) provides a convenient way to interact with papers directly from the terminal. Prefer the CLI over raw API calls when possible.

### Read a paper as markdown

```bash
hf papers read {PAPER_ID}
```

This prints the full paper content as markdown to stdout. It relies on the HTML version of the paper at https://arxiv.org/html/{PAPER_ID}.

There are 2 exceptions:
- Not all arXiv papers have an HTML version. If the HTML version of the paper does not exist, then the content falls back to the HTML of the Hugging Face paper page.
- If the paper is not indexed on hf.co/papers, the command exits with an error: `Paper '{PAPER_ID}' not found on the Hub.`

### Get structured metadata (JSON)

```bash
hf papers info {PAPER_ID}
```

This prints structured JSON metadata that can include:

- authors (names and Hugging Face usernames, in case they have claimed the paper)
- media URLs (uploaded when submitting the paper to Daily Papers)
- summary (abstract) and AI-generated summary
- project page and GitHub repository
- organization and engagement metadata (number of upvotes)

### Search papers

```bash
hf papers search "vision language"
hf papers search "attention mechanism" --limit 10
hf papers search "diffusion" --format json
```

This performs hybrid semantic and full-text search over paper titles, authors, and content.

Options:
- `--limit` (default 20): number of results
- `--format` (`table` or `json`): output format
- `--quiet`: only print paper IDs

### List daily papers

```bash
hf papers ls
hf papers ls --sort trending
hf papers ls --date 2025-01-23
hf papers ls --date today
hf papers ls --week 2025-W09
hf papers ls --month 2025-02
hf papers ls --submitter akhaliq
hf papers ls --format json
```

Options:
- `--date`: date in ISO format (`YYYY-MM-DD`) or `today`
- `--week`: ISO week, e.g. `2025-W09`
- `--month`: month in ISO format, e.g. `2025-02`
- `--submitter`: filter by Hub username of the submitter
- `--sort`: `publishedAt` (default) or `trending`
- `--limit` (default 50): number of results
- `--format` (`table` or `json`): output format
- `--quiet`: only print paper IDs

## Paper Pages REST API

The REST API can be used as an alternative to the CLI, or for endpoints not yet covered by the CLI. All endpoints use the base URL `https://huggingface.co`.

### Fetch the paper page as markdown

```bash
curl -s "https://huggingface.co/papers/{PAPER_ID}.md"
```

Alternatively, you can request markdown from the normal paper page URL:

```bash
curl -s -H "Accept: text/markdown" "https://huggingface.co/papers/{PAPER_ID}"
```

### Get structured metadata

```bash
curl -s "https://huggingface.co/api/papers/{PAPER_ID}"
```

### Find linked models, datasets, and spaces

```bash
curl https://huggingface.co/api/models?filter=arxiv:{PAPER_ID}
curl https://huggingface.co/api/datasets?filter=arxiv:{PAPER_ID}
curl https://huggingface.co/api/spaces?filter=arxiv:{PAPER_ID}
```

### Search papers

```bash
curl -s "https://huggingface.co/api/papers/search?q=vision+language&limit=20"
```

- Endpoint: `GET /api/papers/search`
- Query parameters:
  - `q` (string): search query, max length 250
  - `limit` (integer): number of results, between 1 and 120

### Get daily papers

```bash
curl -s "https://huggingface.co/api/daily_papers?limit=20&date=2025-01-23&sort=publishedAt"
```

- Endpoint: `GET /api/daily_papers`
- Query parameters:
  - `p` (integer): page number
  - `limit` (integer): number of results, between 1 and 100
  - `date` (string): RFC 3339 full-date, for example `2025-01-23`
  - `week` (string): ISO week, for example `2025-W09`
  - `month` (string): month value, for example `2025-02`
  - `submitter` (string): filter by submitter
  - `sort` (enum): `publishedAt` or `trending`

### List papers

```bash
curl -s "https://huggingface.co/api/papers?cursor={CURSOR}&limit=20"
```

- Endpoint: `GET /api/papers`
- Query parameters:
  - `cursor` (string): pagination cursor
  - `limit` (integer): number of results, between 1 and 100

### Claim paper authorship

```bash
curl "https://huggingface.co/api/settings/papers/claim" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer $HF_TOKEN" \
  --data '{
    "paperId": "{PAPER_ID}",
    "claimAuthorId": "{AUTHOR_ENTRY_ID}",
    "targetUserId": "{USER_ID}"
  }'
```

- Endpoint: `POST /api/settings/papers/claim`
- Body:
  - `paperId` (string, required): arXiv paper identifier being claimed
  - `claimAuthorId` (string): author entry on the paper being claimed, 24-char hex ID
  - `targetUserId` (string): HF user who should receive the claim, 24-char hex ID

### Index a paper

Insert a paper from arXiv by ID. If the paper is already indexed, only its authors can re-index it:

```bash
curl "https://huggingface.co/api/papers/index" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer $HF_TOKEN" \
  --data '{
    "arxivId": "{ARXIV_ID}"
  }'
```

- Endpoint: `POST /api/papers/index`
- Body:
  - `arxivId` (string, required): arXiv ID to index, for example `2301.00001`
- Pattern: `^\d{4}\.\d{4,5}$`

### Update paper links

Update the project page, GitHub repository, or submitting organization for a paper. The requester must be the paper author, the Daily Papers submitter, or a papers admin:

```bash
curl "https://huggingface.co/api/papers/{PAPER_OBJECT_ID}/links" \
  --request POST \
  --header "Content-Type: application/json" \
  --header "Authorization: Bearer $HF_TOKEN" \
  --data '{
    "projectPage": "https://example.com",
    "githubRepo": "https://github.com/org/repo",
    "organizationId": "{ORGANIZATION_ID}"
  }'
```

- Endpoint: `POST /api/papers/{paperId}/links`
- Path parameters:
  - `paperId` (string, required): Hugging Face paper object ID
- Body:
  - `githubRepo` (string, nullable): GitHub repository URL
  - `organizationId` (string, nullable): organization ID, 24-char hex ID
  - `projectPage` (string, nullable): project page URL

## Error Handling

- **CLI errors**: `hf papers info` and `hf papers read` print `Paper '{PAPER_ID}' not found on the Hub.` when the paper does not exist.
- **404 on `https://huggingface.co/papers/{PAPER_ID}` or `.md` endpoint**: the paper is not indexed on Hugging Face paper pages yet.
- **404 on `/api/papers/{PAPER_ID}`**: the paper may not be indexed on Hugging Face paper pages yet.
- **Paper ID not found**: verify the extracted arXiv ID, including any version suffix

### Fallbacks

If the Hugging Face paper page does not contain enough detail for the user's question:

- Check the regular paper page at `https://huggingface.co/papers/{PAPER_ID}`
- Fall back to the arXiv page or PDF for the original source:
  - `https://arxiv.org/abs/{PAPER_ID}`
  - `https://arxiv.org/pdf/{PAPER_ID}`

## Notes

- Prefer the `hf papers` CLI for reading, searching, and listing papers.
- No authentication is required for public paper pages (CLI or REST API).
- Write endpoints such as claim authorship, index paper, and update paper links require `Authorization: Bearer $HF_TOKEN` (REST API only, not yet available in the CLI).
- Prefer `hf papers read {PAPER_ID}` or the `.md` endpoint for reliable machine-readable output.
- Prefer `hf papers info {PAPER_ID}` or `/api/papers/{PAPER_ID}` when you need structured JSON fields instead of page markdown.