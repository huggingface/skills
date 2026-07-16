#!/usr/bin/env python3
"""Mirror an ECR Public image to a private ECR repo. Cross-platform.

Needed when SageMaker runs in a VPC without NAT gateway: SageMaker can't pull
from public.ecr.aws in that case, so the image must be in private ECR.

Requires: docker daemon, aws CLI with ecr/ecr-public permissions.
Idempotent: skips push if the tag already exists in the private repo.

Runs `aws`/`docker` from the current shell, inheriting its AWS context — no
Bash/WSL context-sharing problem on Windows.

Usage:
    python mirror_image.py <public-image-uri> <private-repo-name> [<tag-override>]

Prints the resulting private URI to stdout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def log(msg: str) -> None:
    print(f"[mirror_image] {msg}", file=sys.stderr, flush=True)


def require(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        log(f"ERROR: {cmd} not installed or not on PATH")
        sys.exit(1)
    return exe


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def resolve_region() -> str:
    for var in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if os.environ.get(var):
            return os.environ[var]
    proc = run([shutil.which("aws"), "configure", "get", "region"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    if len(sys.argv) < 3:
        log(f"Usage: {os.path.basename(sys.argv[0])} <public-image-uri> <private-repo-name> [<tag-override>]")
        return 64

    public_uri = sys.argv[1]
    private_repo = sys.argv[2]
    tag_override = sys.argv[3] if len(sys.argv) > 3 else ""

    aws = require("aws")
    docker = require("docker")
    if run([docker, "info"]).returncode != 0:
        log("ERROR: docker daemon not running")
        return 1

    # Extract tag
    if tag_override:
        tag = tag_override
    elif ":" in public_uri.rsplit("/", 1)[-1]:
        tag = public_uri.rsplit(":", 1)[-1]
    else:
        log("ERROR: public URI has no tag — refusing implicit ':latest'")
        return 1

    acct = run([aws, "sts", "get-caller-identity", "--query", "Account", "--output", "text"])
    if acct.returncode != 0:
        log("ERROR: 'aws sts get-caller-identity' failed. Configure AWS credentials.")
        return 1
    account_id = acct.stdout.strip()

    region = resolve_region()
    if not region:
        log("ERROR: no AWS region. Set AWS_REGION or configure profile.")
        return 1

    registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    private_uri = f"{registry}/{private_repo}:{tag}"

    log(f"Public : {public_uri}")
    log(f"Private: {private_uri}")

    reg = ["--region", region]

    # Create private repo if missing
    if run([aws, "ecr", "describe-repositories", "--repository-names", private_repo, *reg]).returncode != 0:
        log(f"Creating private ECR repo: {private_repo}")
        run(
            [aws, "ecr", "create-repository", "--repository-name", private_repo,
             "--image-scanning-configuration", "scanOnPush=true", *reg]
        )

    # Skip if tag already exists in private
    if run(
        [aws, "ecr", "describe-images", "--repository-name", private_repo,
         "--image-ids", f"imageTag={tag}", *reg]
    ).returncode == 0:
        log(f"Tag '{tag}' already in private ECR — skipping pull/push")
        print(private_uri)
        return 0

    # Auth. ECR Public auth always uses us-east-1.
    def docker_login(password: str, registry_host: str) -> bool:
        login = subprocess.run(
            [docker, "login", "--username", "AWS", "--password-stdin", registry_host],
            input=password, capture_output=True, text=True,
        )
        return login.returncode == 0

    pub_pw = run([aws, "ecr-public", "get-login-password", "--region", "us-east-1"])
    if pub_pw.returncode != 0 or not docker_login(pub_pw.stdout, "public.ecr.aws"):
        log("ERROR: failed to authenticate to public.ecr.aws")
        return 1

    priv_pw = run([aws, "ecr", "get-login-password", *reg])
    if priv_pw.returncode != 0 or not docker_login(priv_pw.stdout, registry):
        log(f"ERROR: failed to authenticate to {registry}")
        return 1

    log(f"Pulling {public_uri} (may take several minutes)...")
    if subprocess.run([docker, "pull", public_uri]).returncode != 0:
        log("ERROR: docker pull failed")
        return 1
    subprocess.run([docker, "tag", public_uri, private_uri])
    log("Pushing to private ECR...")
    if subprocess.run([docker, "push", private_uri]).returncode != 0:
        log("ERROR: docker push failed")
        return 1

    log("Done.")
    print(private_uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
