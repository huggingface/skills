#!/usr/bin/env python3
"""Tear down a SageMaker endpoint and its associated resources. Cross-platform.

Deletes in safe order: alarms -> autoscaling -> endpoint (stops billing)
-> endpoint config -> model.

Does NOT delete: IAM role, data capture S3 objects, SNS topic, model artifacts.
Idempotent — missing resources are skipped, not errors.

Calls the `aws` CLI from the current shell, so it inherits the same AWS context
(profile, region, SSO session) — no Bash/WSL context-sharing problem on Windows.

Usage:
    python teardown.py <endpoint-name> [<region>]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

RESOURCE_DIM = "sagemaker:variant:DesiredInstanceCount"


def log(msg: str) -> None:
    print(f"[teardown] {msg}", file=sys.stderr, flush=True)


def aws_bin() -> str:
    exe = shutil.which("aws")
    if not exe:
        log("ERROR: the 'aws' CLI was not found on PATH. Install AWS CLI v2.")
        sys.exit(2)
    return exe


def run_aws(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([aws_bin(), *args], capture_output=True, text=True)


def resolve_region(arg_region: str | None) -> str:
    """Region from arg, then env, then the active profile's config."""
    if arg_region:
        return arg_region
    for var in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if os.environ.get(var):
            return os.environ[var]
    proc = run_aws(["configure", "get", "region"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    if len(sys.argv) < 2:
        log(f"Usage: {os.path.basename(sys.argv[0])} <endpoint-name> [<region>]")
        return 64

    endpoint_name = sys.argv[1]
    region = resolve_region(sys.argv[2] if len(sys.argv) > 2 else None)
    if not region:
        log("ERROR: no AWS region. Pass region as 2nd arg or set AWS_REGION.")
        return 1

    reg = ["--region", region]
    log(f"Tearing down endpoint: {endpoint_name} in {region}")

    # Discover what's attached to this endpoint.
    config_name = ""
    model_name = ""
    desc = run_aws(["sagemaker", "describe-endpoint", "--endpoint-name", endpoint_name, *reg])
    endpoint_exists = desc.returncode == 0
    if endpoint_exists:
        try:
            config_name = json.loads(desc.stdout).get("EndpointConfigName", "")
        except json.JSONDecodeError:
            config_name = ""
    else:
        log("Endpoint not found — checking for orphan resources anyway")

    if config_name:
        cfg = run_aws(
            ["sagemaker", "describe-endpoint-config", "--endpoint-config-name", config_name, *reg]
        )
        if cfg.returncode == 0:
            try:
                variants = json.loads(cfg.stdout).get("ProductionVariants", [])
                model_name = variants[0]["ModelName"] if variants else ""
            except (json.JSONDecodeError, KeyError, IndexError):
                model_name = ""

    # Alarms — discover by name prefix. Both real-time and async deploys create
    # alarms named "<endpoint-name>-<something>", so this handles either mode.
    alarms_proc = run_aws(
        ["cloudwatch", "describe-alarms", "--alarm-name-prefix", f"{endpoint_name}-",
         "--query", "MetricAlarms[*].AlarmName", "--output", "json", *reg]
    )
    alarms: list[str] = []
    if alarms_proc.returncode == 0:
        try:
            alarms = json.loads(alarms_proc.stdout) or []
        except json.JSONDecodeError:
            alarms = []
    if alarms:
        run_aws(["cloudwatch", "delete-alarms", "--alarm-names", *alarms, *reg])
        log(f"Deleted alarms: {' '.join(alarms)}")

    # Autoscaling policies — discover all on this variant. Real-time has 1 policy;
    # async has 2 (target-tracking + step-scaling for wake-from-zero).
    resource_id = f"endpoint/{endpoint_name}/variant/AllTraffic"
    policies_proc = run_aws(
        ["application-autoscaling", "describe-scaling-policies",
         "--service-namespace", "sagemaker", "--resource-id", resource_id,
         "--query", "ScalingPolicies[*].PolicyName", "--output", "json", *reg]
    )
    policies: list[str] = []
    if policies_proc.returncode == 0:
        try:
            policies = json.loads(policies_proc.stdout) or []
        except json.JSONDecodeError:
            policies = []
    for policy in policies:
        run_aws(
            ["application-autoscaling", "delete-scaling-policy",
             "--service-namespace", "sagemaker", "--resource-id", resource_id,
             "--scalable-dimension", RESOURCE_DIM, "--policy-name", policy, *reg]
        )
        log(f"Deleted autoscaling policy: {policy}")

    targets = run_aws(
        ["application-autoscaling", "describe-scalable-targets",
         "--service-namespace", "sagemaker", "--resource-ids", resource_id,
         "--query", "ScalableTargets[*].ResourceId", "--output", "json", *reg]
    )
    has_target = False
    if targets.returncode == 0:
        try:
            has_target = resource_id in (json.loads(targets.stdout) or [])
        except json.JSONDecodeError:
            has_target = False
    if has_target:
        run_aws(
            ["application-autoscaling", "deregister-scalable-target",
             "--service-namespace", "sagemaker", "--resource-id", resource_id,
             "--scalable-dimension", RESOURCE_DIM, *reg]
        )
        log("Deregistered scalable target")

    # Endpoint (stops billing)
    if endpoint_exists:
        run_aws(["sagemaker", "delete-endpoint", "--endpoint-name", endpoint_name, *reg])
        log(f"Deleted endpoint: {endpoint_name} (billing stopped)")

    # Endpoint config
    if config_name and run_aws(
        ["sagemaker", "describe-endpoint-config", "--endpoint-config-name", config_name, *reg]
    ).returncode == 0:
        run_aws(["sagemaker", "delete-endpoint-config", "--endpoint-config-name", config_name, *reg])
        log(f"Deleted endpoint config: {config_name}")

    # Model
    if model_name and run_aws(
        ["sagemaker", "describe-model", "--model-name", model_name, *reg]
    ).returncode == 0:
        run_aws(["sagemaker", "delete-model", "--model-name", model_name, *reg])
        log(f"Deleted model: {model_name}")

    log("Teardown complete. Data capture S3 objects (if any) NOT deleted — manage separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
