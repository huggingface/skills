#!/usr/bin/env python3
"""Create a SageMaker execution role. Cross-platform (Windows/macOS/Linux).

Run only after check_role.py confirms no usable role exists.
Requires iam:CreateRole, iam:AttachRolePolicy, iam:PutRolePolicy.

SSO principals typically lack these — this script will fail with AccessDenied
in that case, and the right answer is to ask an AWS admin for a role.

Like check_role.py, this calls `aws` from the current shell so it inherits the
same AWS context (profile, region, SSO session, proxy). Policy documents are
passed inline rather than via `file://` paths, which sidesteps Windows path
translation entirely.

Usage:
    python create_role.py <role-name> [<model-s3-bucket>]

Without bucket, the inline policy keeps a placeholder for later editing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REFERENCES = Path(__file__).resolve().parent.parent / "references"
TRUST_POLICY = REFERENCES / "trust-policy.json"
PERMISSIONS_TEMPLATE = REFERENCES / "minimum-permissions.json"

FULL_ACCESS_ARN = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"


def log(msg: str) -> None:
    print(f"[create_role] {msg}", file=sys.stderr, flush=True)


def aws_bin() -> str:
    exe = shutil.which("aws")
    if not exe:
        log("ERROR: the 'aws' CLI was not found on PATH. Install AWS CLI v2.")
        sys.exit(2)
    return exe


def run_aws(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run([aws_bin(), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        log(f"AWS command failed: aws {' '.join(args)}")
        if proc.stderr.strip():
            log(proc.stderr.strip())
        sys.exit(1)
    return proc


def main() -> int:
    if len(sys.argv) < 2:
        log(f"Usage: {Path(sys.argv[0]).name} <role-name> [<model-s3-bucket>]")
        return 64

    role_name = sys.argv[1]
    model_bucket = sys.argv[2] if len(sys.argv) > 2 else ""

    if run_aws(["iam", "get-role", "--role-name", role_name]).returncode == 0:
        log(f"Role '{role_name}' already exists. Use check_role.py to validate it.")
        return 1

    ident = run_aws(["sts", "get-caller-identity", "--query", "Arn", "--output", "text"], check=True)
    caller_arn = ident.stdout.strip()
    if ":assumed-role/AWSReservedSSO_" in caller_arn:
        log(f"WARNING: SSO caller ({caller_arn}) — IAM creation likely to fail with AccessDenied.")
        log("If it does, ask an AWS admin to create the role.")

    trust_doc = TRUST_POLICY.read_text(encoding="utf-8")

    log(f"Creating role: {role_name}")
    run_aws(
        [
            "iam", "create-role",
            "--role-name", role_name,
            "--assume-role-policy-document", trust_doc,
            "--description", "SageMaker execution role (hf-cloud-sagemaker-iam-preflight skill)",
        ],
        check=True,
    )

    log("Attaching AmazonSageMakerFullAccess")
    run_aws(
        ["iam", "attach-role-policy", "--role-name", role_name, "--policy-arn", FULL_ACCESS_ARN],
        check=True,
    )

    inline_policy = PERMISSIONS_TEMPLATE.read_text(encoding="utf-8")
    if model_bucket:
        inline_policy = inline_policy.replace("REPLACE_WITH_MODEL_BUCKET", model_bucket)
        log(f"Inline policy will grant S3 access to: {model_bucket}")
    else:
        log("WARNING: No model bucket specified — policy contains placeholder.")
        log("Update before deployment, or pass the bucket name as the 2nd argument.")

    log("Attaching inline policy: SageMakerDeploymentMinimum")
    run_aws(
        [
            "iam", "put-role-policy",
            "--role-name", role_name,
            "--policy-name", "SageMakerDeploymentMinimum",
            "--policy-document", inline_policy,
        ],
        check=True,
    )

    arn = run_aws(
        ["iam", "get-role", "--role-name", role_name, "--query", "Role.Arn", "--output", "text"],
        check=True,
    ).stdout.strip()
    log(f"Created: {arn}")
    print(arn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
