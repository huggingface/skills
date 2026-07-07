---
name: hf-cloud-sagemaker-iam-preflight
description: 'Ensure a usable SageMaker execution role exists before deploying or training. Use this skill whenever about to create a SageMaker endpoint, model, training job, or any resource that requires an execution role. Use it especially when the user has not provided a role ARN explicitly, when scripts are about to call `iam:CreateRole`, or when an AccessDenied error mentions an IAM action. Never blindly call `iam:CreateRole` — always check for existing roles first. This skill prevents the most common SageMaker deployment failure: trying to create IAM resources from an SSO principal that has no IAM write permissions.'
---

# SageMaker IAM Preflight

Every SageMaker resource needs an **execution role** — the IAM role SageMaker assumes to read model artifacts from S3, pull serving containers from ECR, and write logs. Most deployments fail here because the script tried to create a new role without checking if a usable one already existed, then blew up because the caller is an SSO principal.

This skill encodes the right order: discover, validate, only create if necessary.

## Running the helpers (cross-platform)

The helpers are Python so they run identically on Windows, macOS, and Linux:

```bash
python3 scripts/check_role.py        # macOS / Linux
python  scripts/check_role.py        # Windows (PowerShell / cmd)
```

**Run them from the shell where the AWS CLI already works** — i.e. wherever `aws sts get-caller-identity` succeeds. The script shells out to that same `aws` binary and inherits the shell's profile, region, SSO session, proxy, and credential chain.

> **Windows / WSL / Git Bash caveat.** Do **not** invoke these through a Bash shim (WSL, Git Bash, MSYS) on Windows. Those Bash environments frequently do **not** share the Windows AWS config, credentials, SSO sessions, environment variables, or proxy settings — so `aws sts get-caller-identity` fails inside Bash even when it works natively in PowerShell. (This is exactly why the old `.sh` helpers failed on Windows and were replaced with Python.) If you're in PowerShell, run `python ...\check_role.py` directly in PowerShell. If the helper still can't see your identity, run the same discovery natively (see "Native AWS CLI equivalent" below) in the shell where `aws sts get-caller-identity` returns your ARN.

## Order of operations

### Step 1 — Did the user provide a role?

Validate that one specifically:

```bash
python3 scripts/check_role.py "<role-name-or-arn>"
```

On success it prints the ARN to stdout (exit 0). On failure it logs why on stderr. Don't try to silently fix a broken role — surface the problem.

### Step 2 — Discover existing roles

```bash
python3 scripts/check_role.py
```

Lists roles matching common SageMaker patterns (`AmazonSageMaker-ExecutionRole-*`, `SageMakerExecutionRole*`, etc.), **ranks by last-used date** (most recent first), validates trust policy in that order, returns the first usable ARN. Most accounts that have used SageMaker before already have one.

Why rank by last-used: in accounts with multiple roles (auto-generated 2021 role + manual project role + etc.), the alphabetically-first one is rarely the actively-maintained one. The most-recently-used role is more likely to have current policies — including cross-account ECR pull. The script prints the ranking so you can see which got picked.

IAM frequently reports **no** `RoleLastUsed` at all (tracking only covers recent activity). When every candidate ties at "never used", the script falls back to **newest creation date** — a newer role is more likely to have current policies than a 2021 leftover.

### Step 3 — Create, only if discovery found nothing

**If the user can create** (has IAM permissions):

```bash
python3 scripts/create_role.py "<role-name>" "<model-bucket>"
```

Second arg scopes S3 access to a specific bucket. Omit if unknown; script warns and the user can update the policy later.

**If the user cannot create** (SSO principal — `hf-cloud-aws-context-discovery` will have flagged this):

Stop and surface this clearly. Don't retry alternative IAM operations hoping one works:

> I can't find an existing SageMaker execution role, and you're authenticated via SSO so you can't create one directly. Please either:
>   - Ask your AWS admin for a SageMaker execution role ARN, or
>   - Have them grant your SSO permission set `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`

Specific instructions get unblocked fast; vague "permission denied" messages don't.

## What "validated" means

A role is usable when (1) it exists, (2) its trust policy allows `sagemaker.amazonaws.com` to `sts:AssumeRole` — see `references/trust-policy.json` for the canonical form.

`check_role.py` verifies these two. It does **not** deep-check permissions because comprehensive analysis is expensive (`iam:SimulatePrincipalPolicy` per action) and most existing SageMaker roles are over-permissioned via `AmazonSageMakerFullAccess`. If you suspect a permissions issue at deploy time, the deployment error will tell you which action was denied — fix it then, not preemptively.

## Minimum permissions

`references/minimum-permissions.json` covers what SageMaker actually needs:
- `s3:GetObject` + `s3:ListBucket` on the model artifact bucket
- ECR pull permissions
- CloudWatch logs and metrics

Layered on top of `AmazonSageMakerFullAccess` (attached by `create_role.py`). Replace `REPLACE_WITH_MODEL_BUCKET` in the template with the actual bucket name — `create_role.py` does this automatically when given a bucket as its second argument.

## Native AWS CLI equivalent (fallback)

If the Python helper can't run or can't see your identity (rare — usually a broken PATH or running under a Bash shim that lacks AWS context), do the same preflight by hand in the shell where `aws sts get-caller-identity` works. The logic is just AWS CLI calls; the helper exists only to bundle and rank them.

PowerShell:

```powershell
# 1. List candidate SageMaker roles
aws iam list-roles --query "Roles[?contains(RoleName,'SageMaker') || contains(RoleName,'sagemaker')]" --output json

# 2. For each candidate, confirm the trust policy allows sagemaker.amazonaws.com
aws iam get-role --role-name <role-name> --query "Role.AssumeRolePolicyDocument" --output json

# 3. Prefer the most-recently-used role with SageMaker-execution naming
#    (LastUsedDate is often None for every role — then prefer newest CreateDate)
aws iam get-role --role-name <role-name> --query "Role.[RoleLastUsed.LastUsedDate, CreateDate]" --output text
```

Pick the most-recently-used role whose trust policy contains `sagemaker.amazonaws.com`. Use the resulting ARN exactly as if `check_role.py` had returned it. Bash/macOS/Linux use the same commands.
