"""Shared helpers for the deployment scripts (deploy.py, deploy_async.py).

Anything that should look identical between real-time and async deployments
lives here — tag schema, name format, env-var parsing, model creation,
endpoint waiting. Mode-specific logic (endpoint config shape, autoscaling
policies, alarm metrics) stays in the calling script.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError


# Shared tagging convention. CreatedBy lets us find every resource these
# scripts have ever created via:
#   aws resourcegroupstaggingapi get-resources \
#     --tag-filters Key=CreatedBy,Values=agentic-deploy-skills
CREATED_BY_TAG_VALUE = "agentic-deploy-skills"


def log(prefix: str, msg: str) -> None:
    """Stream a log line to stderr with a per-script prefix."""
    print(f"[{prefix}] {msg}", file=sys.stderr, flush=True)


def parse_env(env_args: list[str]) -> dict[str, str]:
    """Parse --env KEY=VALUE flags from argparse into a dict."""
    env: dict[str, str] = {}
    for item in env_args:
        if "=" not in item:
            raise SystemExit(f"--env must be KEY=VALUE, got: {item}")
        k, v = item.split("=", 1)
        env[k] = v
    return env


def make_endpoint_name(model_name: str, override: str | None) -> str:
    """Generate a SageMaker-legal endpoint name.

    Default format: <model-name>-<YYYYMMDD-HHMM>. SageMaker names are limited
    to 63 chars and must be DNS-friendly (lowercase, hyphens, no underscores).
    """
    if override:
        return override
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    base = model_name.replace("_", "-").lower()
    return f"{base}-{stamp}"[:63]


def build_tags(
    *,
    project: str,
    caller_arn: str,
    environment: str,
    model_s3_uri: str | None = None,
    extra: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build the shared tag set applied to every resource we create.

    `extra` lets the caller add deployment-mode-specific tags (e.g.
    `{"InferenceMode": "async"}`) without forking the schema.
    """
    owner = caller_arn.split("/")[-1] if "/" in caller_arn else caller_arn
    tags = [
        {"Key": "Project", "Value": project},
        {"Key": "Owner", "Value": owner},
        {"Key": "Environment", "Value": environment},
        {"Key": "CreatedBy", "Value": CREATED_BY_TAG_VALUE},
    ]
    if model_s3_uri:
        tags.append({"Key": "ModelArtifact", "Value": model_s3_uri})
    if extra:
        for k, v in extra.items():
            tags.append({"Key": k, "Value": v})
    return tags


def create_model(
    sm: Any,
    *,
    model_name: str,
    image_uri: str,
    role_arn: str,
    model_s3_uri: str | None,
    env: dict[str, str],
    tags: list[dict[str, str]],
    log_prefix: str = "deploy",
) -> str:
    """Create a SageMaker Model. Idempotent — reuses on AlreadyExists.

    Returns the model name on success. The model definition itself is mode-
    independent: same call, same parameters, whether the eventual endpoint
    is real-time or async.
    """
    log(log_prefix, f"Creating model: {model_name}")
    primary_container: dict[str, Any] = {"Image": image_uri}
    if env:
        primary_container["Environment"] = env
    if model_s3_uri:
        primary_container["ModelDataUrl"] = model_s3_uri

    try:
        sm.create_model(
            ModelName=model_name,
            PrimaryContainer=primary_container,
            ExecutionRoleArn=role_arn,
            Tags=tags,
        )
    except ClientError as e:
        if "Cannot create already existing model" in str(e):
            log(log_prefix, f"Model {model_name} already exists — reusing")
        else:
            raise
    return model_name


def wait_for_endpoint(
    sm: Any,
    endpoint_name: str,
    timeout_minutes: int = 30,
    log_prefix: str = "deploy",
) -> None:
    """Poll DescribeEndpoint until InService, or raise on Failed/timeout."""
    log(log_prefix, f"Waiting for {endpoint_name} to reach InService (up to {timeout_minutes} min)...")
    start = time.time()
    deadline = start + (timeout_minutes * 60)

    while time.time() < deadline:
        resp = sm.describe_endpoint(EndpointName=endpoint_name)
        status = resp["EndpointStatus"]
        elapsed = int(time.time() - start)

        if status == "InService":
            log(log_prefix, f"InService after {elapsed}s")
            return
        if status == "Failed":
            reason = resp.get("FailureReason", "(no reason given)")
            raise RuntimeError(f"Endpoint creation failed after {elapsed}s: {reason}")

        log(log_prefix, f"  status={status} elapsed={elapsed}s")
        time.sleep(30)

    raise TimeoutError(f"Endpoint did not reach InService within {timeout_minutes} minutes")
