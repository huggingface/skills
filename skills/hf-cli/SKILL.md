---
name: hf-cli
description: "Hugging Face Hub CLI (`hf`) for downloading, uploading, and managing models, datasets, spaces, buckets, repos, papers, jobs, and more on the Hugging Face Hub. Use when: handling authentication; managing local cache; managing Hugging Face Buckets; running or scheduling jobs on Hugging Face infrastructure; managing Hugging Face repos; discussions and pull requests; browsing models, datasets and spaces; reading, searching, or browsing academic papers; managing collections; querying datasets; configuring spaces; setting up webhooks; or deploying and managing HF Inference Endpoints. Make sure to use this skill whenever the user mentions 'hf', 'huggingface', 'Hugging Face', 'huggingface-cli', or 'hugging face cli', or wants to do anything related to the Hugging Face ecosystem and to AI and ML in general. Also use for cloud storage needs like training checkpoints, data pipelines, or agent traces. Use even if the user doesn't explicitly ask for a CLI command. Replaces the deprecated `huggingface-cli`."
---

Install: `curl -LsSf https://hf.co/cli/install.sh | bash -s`.

The Hugging Face Hub CLI tool `hf` is available. IMPORTANT: The `hf` command replaces the deprecated `huggingface-cli` command.

Use `hf --help` to view available functions. Note that auth commands are now all under `hf auth` e.g. `hf auth whoami`.

Generated with `huggingface_hub v1.15.0`. Run `hf skills add --force` to regenerate.

## Commands

- `hf download REPO_ID` — Download files from the Hub. `[--type CHOICE --revision TEXT --include TEXT --exclude TEXT --cache-dir TEXT --local-dir TEXT --force-download --dry-run --max-workers INTEGER --format CHOICE]`
- `hf env` — Print information about the environment. `[--format CHOICE]`
- `hf sync` — Sync files between local directory and a bucket. `[--delete --ignore-times --ignore-sizes --plan TEXT --apply TEXT --dry-run --include TEXT --exclude TEXT --filter-from TEXT --existing --ignore-existing --verbose --format CHOICE]`
- `hf update` — Update the `hf` CLI to the latest version. `[--format CHOICE]`
- `hf upload REPO_ID` — Upload a file or a folder to the Hub. Recommended for single-commit uploads. `[--type CHOICE --revision TEXT --private --include TEXT --exclude TEXT --delete TEXT --commit-message TEXT --commit-description TEXT --create-pr --every FLOAT --format CHOICE]`
- `hf upload-large-folder REPO_ID LOCAL_PATH` — Upload a large folder to the Hub. Recommended for resumable uploads. `[--type CHOICE --revision TEXT --private --include TEXT --exclude TEXT --num-workers INTEGER --no-report --no-bars --format CHOICE]`
- `hf version` — Print information about the hf version. `[--format CHOICE]`

### `hf auth` — Manage authentication (login, logout, etc.).

- `hf auth list` — List all stored access tokens. `[--format CHOICE]`
- `hf auth login` — Login using a token from huggingface.co/settings/tokens. `[--add-to-git-credential --force --format CHOICE]`
- `hf auth logout` — Logout from a specific token. `[--token-name TEXT --format CHOICE]`
- `hf auth switch` — Switch between access tokens. `[--token-name TEXT --add-to-git-credential --format CHOICE]`
- `hf auth token` — Print the current access token to stdout. `[--format CHOICE]`
- `hf auth whoami` — Find out which huggingface.co account you are logged in as. `[--format CHOICE]`

### `hf buckets` — Commands to interact with buckets.

- `hf buckets cp SRC` — Copy files to or from buckets. `[--format CHOICE]`
- `hf buckets create BUCKET_ID` — Create a new bucket. `[--private --region CHOICE --exist-ok --format CHOICE]`
- `hf buckets delete BUCKET_ID` — Delete a bucket. `[--yes --missing-ok --format CHOICE]`
- `hf buckets info BUCKET_ID` — Get info about a bucket. `[--format CHOICE]`
- `hf buckets list` — List buckets or files in a bucket. `[--human-readable --tree --recursive --search TEXT --format CHOICE]`
- `hf buckets move FROM_ID TO_ID` — Move (rename) a bucket to a new name or namespace. `[--format CHOICE]`
- `hf buckets remove ARGUMENT` — Remove files from a bucket. `[--recursive --yes --dry-run --include TEXT --exclude TEXT --format CHOICE]`
- `hf buckets sync` — Sync files between local directory and a bucket. `[--delete --ignore-times --ignore-sizes --plan TEXT --apply TEXT --dry-run --include TEXT --exclude TEXT --filter-from TEXT --existing --ignore-existing --verbose --format CHOICE]`

### `hf cache` — Manage local cache directory.

- `hf cache list` — List cached repositories or revisions. `[--cache-dir TEXT --revisions --filter TEXT --sort CHOICE --limit INTEGER --format CHOICE]`
- `hf cache prune` — Remove detached revisions from the cache. `[--cache-dir TEXT --yes --dry-run --format CHOICE]`
- `hf cache rm TARGETS` — Remove cached repositories or revisions. `[--cache-dir TEXT --yes --dry-run --format CHOICE]`
- `hf cache verify REPO_ID` — Verify checksums for a single repo revision from cache or a local directory. `[--type CHOICE --revision TEXT --cache-dir TEXT --local-dir TEXT --fail-on-missing-files --fail-on-extra-files --format CHOICE]`

### `hf collections` — Interact with collections on the Hub.

- `hf collections add-item COLLECTION_SLUG ITEM_ID ITEM_TYPE` — Add an item to a collection. `[--note TEXT --exists-ok --format CHOICE]`
- `hf collections create TITLE` — Create a new collection on the Hub. `[--namespace TEXT --description TEXT --private --exists-ok --format CHOICE]`
- `hf collections delete COLLECTION_SLUG` — Delete a collection from the Hub. `[--missing-ok --format CHOICE]`
- `hf collections delete-item COLLECTION_SLUG ITEM_OBJECT_ID` — Delete an item from a collection. `[--missing-ok --format CHOICE]`
- `hf collections info COLLECTION_SLUG` — Get info about a collection on the Hub. `[--format CHOICE]`
- `hf collections list` — List collections on the Hub. `[--owner TEXT --item TEXT --sort CHOICE --limit INTEGER --format CHOICE]`
- `hf collections update COLLECTION_SLUG` — Update a collection's metadata on the Hub. `[--title TEXT --description TEXT --position INTEGER --private --theme TEXT --format CHOICE]`
- `hf collections update-item COLLECTION_SLUG ITEM_OBJECT_ID` — Update an item in a collection. `[--note TEXT --position INTEGER --format CHOICE]`

### `hf datasets` — Interact with datasets on the Hub.

- `hf datasets card DATASET_ID` — Get the dataset card (README) for a dataset on the Hub. `[--metadata --text --format CHOICE]`
- `hf datasets info DATASET_ID` — Get info about a dataset on the Hub. `[--revision TEXT --expand TEXT --format CHOICE]`
- `hf datasets leaderboard DATASET_ID` — List model scores from a dataset leaderboard. This command helps find the best models for a task or compare models by benchmark scores. Use 'hf datasets ls --filter benchmark:official' to list available leaderboards. `[--limit INTEGER --format CHOICE]`
- `hf datasets list` — List datasets on the Hub, or files in a dataset repo. `[--search TEXT --author TEXT --filter TEXT --sort CHOICE --limit INTEGER --expand TEXT --human-readable --tree --recursive --revision TEXT --format CHOICE]`
- `hf datasets parquet DATASET_ID` — List parquet file URLs available for a dataset. `[--subset TEXT --split TEXT --format CHOICE]`
- `hf datasets sql SQL` — Execute a raw SQL query with DuckDB against dataset parquet URLs. `[--format CHOICE]`

### `hf discussions` — Manage discussions and pull requests on the Hub.

- `hf discussions close REPO_ID NUM` — Close a discussion or pull request. `[--comment TEXT --yes --type CHOICE --format CHOICE]`
- `hf discussions comment REPO_ID NUM` — Comment on a discussion or pull request. `[--body TEXT --body-file PATH --type CHOICE --format CHOICE]`
- `hf discussions create REPO_ID --title TEXT` — Create a new discussion or pull request on a repo. `[--body TEXT --body-file PATH --pull-request --type CHOICE --format CHOICE]`
- `hf discussions diff REPO_ID NUM` — Show the diff of a pull request. `[--type CHOICE --format CHOICE]`
- `hf discussions info REPO_ID NUM` — Get info about a discussion or pull request. `[--type CHOICE --format CHOICE]`
- `hf discussions list REPO_ID` — List discussions and pull requests on a repo. `[--status CHOICE --kind CHOICE --author TEXT --limit INTEGER --type CHOICE --format CHOICE]`
- `hf discussions merge REPO_ID NUM` — Merge a pull request. `[--comment TEXT --yes --type CHOICE --format CHOICE]`
- `hf discussions rename REPO_ID NUM NEW_TITLE` — Rename a discussion or pull request. `[--type CHOICE --format CHOICE]`
- `hf discussions reopen REPO_ID NUM` — Reopen a closed discussion or pull request. `[--comment TEXT --yes --type CHOICE --format CHOICE]`

### `hf endpoints` — Manage Hugging Face Inference Endpoints.

- `hf endpoints catalog deploy --repo TEXT` — Deploy an Inference Endpoint from the Model Catalog. `[--name TEXT --accelerator TEXT --namespace TEXT --format CHOICE]`
- `hf endpoints catalog list` — List available Catalog models. `[--format CHOICE]`
- `hf endpoints delete NAME` — Delete an Inference Endpoint permanently. `[--namespace TEXT --yes --format CHOICE]`
- `hf endpoints deploy NAME --repo TEXT --framework TEXT --accelerator TEXT --instance-size TEXT --instance-type TEXT --region TEXT --vendor TEXT` — Deploy an Inference Endpoint from a Hub repository. `[--namespace TEXT --task TEXT --min-replica INTEGER --max-replica INTEGER --scale-to-zero-timeout INTEGER --scaling-metric CHOICE --scaling-threshold FLOAT --format CHOICE]`
- `hf endpoints describe NAME` — Get information about an existing endpoint. `[--namespace TEXT --format CHOICE]`
- `hf endpoints list` — Lists all Inference Endpoints for the given namespace. `[--namespace TEXT --format CHOICE]`
- `hf endpoints pause NAME` — Pause an Inference Endpoint. `[--namespace TEXT --format CHOICE]`
- `hf endpoints resume NAME` — Resume an Inference Endpoint. `[--namespace TEXT --fail-if-already-running --format CHOICE]`
- `hf endpoints scale-to-zero NAME` — Scale an Inference Endpoint to zero. `[--namespace TEXT --format CHOICE]`
- `hf endpoints update NAME` — Update an existing endpoint. `[--namespace TEXT --repo TEXT --accelerator TEXT --instance-size TEXT --instance-type TEXT --framework TEXT --revision TEXT --task TEXT --min-replica INTEGER --max-replica INTEGER --scale-to-zero-timeout INTEGER --scaling-metric CHOICE --scaling-threshold FLOAT --format CHOICE]`

### `hf extensions` — Manage hf CLI extensions.

- `hf extensions exec NAME` — Execute an installed extension.
- `hf extensions install REPO_ID` — Install an extension from a public GitHub repository. `[--force --format CHOICE]`
- `hf extensions list` — List installed extension commands. `[--format CHOICE]`
- `hf extensions remove NAME` — Remove an installed extension. `[--format CHOICE]`
- `hf extensions search` — Search extensions available on GitHub (tagged with 'hf-extension' topic). `[--format CHOICE]`

### `hf jobs` — Run and manage Jobs on the Hub.

- `hf jobs cancel JOB_ID` — Cancel a Job `[--namespace TEXT --format CHOICE]`
- `hf jobs hardware` — List available hardware options for Jobs `[--format CHOICE]`
- `hf jobs inspect JOB_IDS` — Display detailed information on one or more Jobs `[--namespace TEXT --format CHOICE]`
- `hf jobs logs JOB_ID` — Fetch the logs of a Job. `[--follow --tail INTEGER --namespace TEXT --format CHOICE]`
- `hf jobs ps` — List Jobs. `[--all --namespace TEXT --filter TEXT --format TEXT --quiet]`
- `hf jobs run IMAGE COMMAND` — Run a Job. `[--env TEXT --secrets TEXT --label TEXT --volume TEXT --env-file TEXT --secrets-file TEXT --flavor CHOICE --timeout TEXT --detach --namespace TEXT]`
- `hf jobs scheduled delete SCHEDULED_JOB_ID` — Delete a scheduled Job. `[--namespace TEXT --format CHOICE]`
- `hf jobs scheduled inspect SCHEDULED_JOB_IDS` — Display detailed information on one or more scheduled Jobs `[--namespace TEXT --format CHOICE]`
- `hf jobs scheduled ps` — List scheduled Jobs `[--all --namespace TEXT --filter TEXT --format TEXT --quiet]`
- `hf jobs scheduled resume SCHEDULED_JOB_ID` — Resume (unpause) a scheduled Job. `[--namespace TEXT --format CHOICE]`
- `hf jobs scheduled run SCHEDULE IMAGE COMMAND` — Schedule a Job. `[--suspend --concurrency --env TEXT --secrets TEXT --label TEXT --volume TEXT --env-file TEXT --secrets-file TEXT --flavor CHOICE --timeout TEXT --namespace TEXT]`
- `hf jobs scheduled suspend SCHEDULED_JOB_ID` — Suspend (pause) a scheduled Job. `[--namespace TEXT --format CHOICE]`
- `hf jobs scheduled uv run SCHEDULE SCRIPT` — Run a UV script (local file or URL) on HF infrastructure `[--suspend --concurrency --image TEXT --flavor CHOICE --env TEXT --secrets TEXT --label TEXT --volume TEXT --env-file TEXT --secrets-file TEXT --timeout TEXT --namespace TEXT --with TEXT --python TEXT]`
- `hf jobs stats` — Fetch the resource usage statistics and metrics of Jobs `[--namespace TEXT --format CHOICE]`
- `hf jobs uv run SCRIPT` — Run a UV script (local file or URL) on HF infrastructure `[--image TEXT --flavor CHOICE --env TEXT --secrets TEXT --label TEXT --volume TEXT --env-file TEXT --secrets-file TEXT --timeout TEXT --detach --namespace TEXT --with TEXT --python TEXT]`

### `hf models` — Interact with models on the Hub.

- `hf models card MODEL_ID` — Get the model card (README) for a model on the Hub. `[--metadata --text --format CHOICE]`
- `hf models info MODEL_ID` — Get info about a model on the Hub. `[--revision TEXT --expand TEXT --format CHOICE]`
- `hf models list` — List models on the Hub, or files in a model repo. `[--search TEXT --author TEXT --filter TEXT --num-parameters TEXT --sort CHOICE --limit INTEGER --expand TEXT --human-readable --tree --recursive --revision TEXT --format CHOICE]`

### `hf papers` — Interact with papers on the Hub.

- `hf papers info PAPER_ID` — Get info about a paper on the Hub. `[--format CHOICE]`
- `hf papers list` — List daily papers on the Hub. `[--date TEXT --week TEXT --month TEXT --submitter TEXT --sort CHOICE --limit INTEGER --format CHOICE]`
- `hf papers read PAPER_ID` — Read a paper as markdown. `[--format CHOICE]`
- `hf papers search QUERY` — Search papers on the Hub. `[--limit INTEGER --format CHOICE]`

### `hf repos` — Manage repos on the Hub.

- `hf repos branch create REPO_ID BRANCH` — Create a new branch for a repo on the Hub. `[--revision TEXT --type CHOICE --exist-ok --format CHOICE]`
- `hf repos branch delete REPO_ID BRANCH` — Delete a branch from a repo on the Hub. `[--type CHOICE --format CHOICE]`
- `hf repos create REPO_ID` — Create a new repo on the Hub. `[--type CHOICE --space-sdk TEXT --private --public --protected --exist-ok --resource-group-id TEXT --region CHOICE --flavor CHOICE --storage CHOICE --sleep-time INTEGER --secrets TEXT --secrets-file TEXT --env TEXT --env-file TEXT --volume TEXT --format CHOICE]`
- `hf repos delete REPO_ID` — Delete a repo from the Hub. This is an irreversible operation. `[--type CHOICE --missing-ok --yes --format CHOICE]`
- `hf repos delete-files REPO_ID PATTERNS` — Delete files from a repo on the Hub. `[--type CHOICE --revision TEXT --commit-message TEXT --commit-description TEXT --create-pr --format CHOICE]`
- `hf repos duplicate FROM_ID` — Duplicate a repo on the Hub (model, dataset, or Space). `[--type CHOICE --private --public --protected --exist-ok --flavor CHOICE --storage CHOICE --sleep-time INTEGER --secrets TEXT --secrets-file TEXT --env TEXT --env-file TEXT --volume TEXT --format CHOICE]`
- `hf repos move FROM_ID TO_ID` — Move a repository from a namespace to another namespace. `[--type CHOICE --format CHOICE]`
- `hf repos settings REPO_ID` — Update the settings of a repository. `[--gated CHOICE --private --public --protected --type CHOICE --format CHOICE]`
- `hf repos tag create REPO_ID TAG` — Create a tag for a repo. `[--message TEXT --revision TEXT --type CHOICE --format CHOICE]`
- `hf repos tag delete REPO_ID TAG` — Delete a tag for a repo. `[--yes --type CHOICE --format CHOICE]`
- `hf repos tag list REPO_ID` — List tags for a repo. `[--type CHOICE --format CHOICE]`

### `hf skills` — Manage skills for AI assistants.

- `hf skills add` — Download a Hugging Face skill and install it for an AI assistant. `[--claude --global --dest PATH --force --format CHOICE]`
- `hf skills list` — List available skills from the Hugging Face marketplace. `[--format CHOICE]`
- `hf skills preview` — Print the generated `hf-cli` SKILL.md to stdout. `[--format CHOICE]`
- `hf skills update` — Update installed Hugging Face marketplace skills. `[--claude --global --dest PATH --format CHOICE]`

### `hf spaces` — Interact with spaces on the Hub.

- `hf spaces card SPACE_ID` — Get the Space card (README) for a Space on the Hub. `[--metadata --text --format CHOICE]`
- `hf spaces dev-mode SPACE_ID` — Enable or disable dev mode on a Space. `[--stop --format CHOICE]`
- `hf spaces hardware` — List available hardware options for Spaces. `[--format CHOICE]`
- `hf spaces hot-reload SPACE_ID` — Hot-reload any Python file of a Space without a full rebuild + restart. `[--local-file PATH --skip-checks --skip-summary --format CHOICE]`
- `hf spaces info SPACE_ID` — Get info about a space on the Hub. `[--revision TEXT --expand TEXT --format CHOICE]`
- `hf spaces list` — List spaces on the Hub, or files in a space repo. `[--search TEXT --author TEXT --filter TEXT --sort CHOICE --limit INTEGER --expand TEXT --human-readable --tree --recursive --revision TEXT --format CHOICE]`
- `hf spaces logs SPACE_ID` — Fetch the run or build logs of a Space. `[--build --follow --tail INTEGER --format CHOICE]`
- `hf spaces pause SPACE_ID` — Pause a Space. `[--format CHOICE]`
- `hf spaces restart SPACE_ID` — Restart a Space. `[--factory-reboot --format CHOICE]`
- `hf spaces search QUERY` — Search spaces on the Hub using semantic search. `[--filter TEXT --sdk TEXT --include-non-running --description --limit INTEGER --format CHOICE]`
- `hf spaces secrets add SPACE_ID` — Add or update secrets for a Space. `[--secrets TEXT --secrets-file TEXT --format CHOICE]`
- `hf spaces secrets delete SPACE_ID KEY` — Remove a secret from a Space. `[--yes --format CHOICE]`
- `hf spaces secrets list SPACE_ID` — List secrets for a Space. Secret values are write-only and not returned. `[--format CHOICE]`
- `hf spaces settings SPACE_ID` — Update the settings of a Space. `[--sleep-time INTEGER --hardware CHOICE --format CHOICE]`
- `hf spaces variables add SPACE_ID` — Add or update environment variables for a Space. `[--env TEXT --env-file TEXT --format CHOICE]`
- `hf spaces variables delete SPACE_ID KEY` — Remove an environment variable from a Space. `[--yes --format CHOICE]`
- `hf spaces variables list SPACE_ID` — List environment variables for a Space. `[--format CHOICE]`
- `hf spaces volumes delete SPACE_ID` — Remove all volumes from a Space. `[--yes --format CHOICE]`
- `hf spaces volumes list SPACE_ID` — List volumes mounted in a Space. `[--format CHOICE]`
- `hf spaces volumes set SPACE_ID` — Set (replace) volumes for a Space. `[--volume TEXT --format CHOICE]`

### `hf webhooks` — Manage webhooks on the Hub.

- `hf webhooks create --watch TEXT` — Create a new webhook. `[--url TEXT --job-id TEXT --domain CHOICE --secret TEXT --format CHOICE]`
- `hf webhooks delete WEBHOOK_ID` — Delete a webhook permanently. `[--yes --format CHOICE]`
- `hf webhooks disable WEBHOOK_ID` — Disable an active webhook. `[--format CHOICE]`
- `hf webhooks enable WEBHOOK_ID` — Enable a disabled webhook. `[--format CHOICE]`
- `hf webhooks info WEBHOOK_ID` — Show full details for a single webhook. `[--format CHOICE]`
- `hf webhooks list` — List all webhooks for the current user. `[--format CHOICE]`
- `hf webhooks update WEBHOOK_ID` — Update an existing webhook. Only provided options are changed. `[--url TEXT --watch TEXT --domain CHOICE --secret TEXT --format CHOICE]`

## Common options

- `--format` — Output format: `--format json` (or `--json`) or `--format table` (default).
- `-q / --quiet` — Print only IDs (one per line).
- `--revision` — Git revision id which can be a branch name, a tag, or a commit hash.
- `--token` — Use a User Access Token. Prefer setting `HF_TOKEN` env var instead of passing `--token`.
- `--type` — The type of repository (model, dataset, or space).

## Mounting repos as local filesystems

To mount Hub repositories or buckets as local filesystems — no download, no copy, no waiting — use `hf-mount`. Files are fetched on demand. GitHub: https://github.com/huggingface/hf-mount

Install: `curl -fsSL https://raw.githubusercontent.com/huggingface/hf-mount/main/install.sh | sh`

Some command examples:
- `hf-mount start repo openai-community/gpt2 /tmp/gpt2` — mount a repo (read-only)
- `hf-mount start --hf-token $HF_TOKEN bucket myuser/my-bucket /tmp/data` — mount a bucket (read-write)
- `hf-mount status` / `hf-mount stop /tmp/data` — list or unmount

## Tips

- Use `hf <command> --help` for full options, descriptions, usage, and real-world examples
- Authenticate with `HF_TOKEN` env var (recommended) or with `--token`
- Update the CLI with `hf update` (uses the correct command for the detected install method)
