#!/usr/bin/env python3
"""Tear down a SageMaker endpoint and its associated resources. Cross-platform.

Deletes in safe order: alarms -> autoscaling -> inference components ->
endpoint (stops billing) -> endpoint config -> model.

Handles both deployment shapes:
  - model-based endpoints (deploy.py, deploy_async.py): the variant carries the
    model, autoscaling targets endpoint/<name>/variant/AllTraffic
  - inference-component endpoints (deploy_ic.py, scale-to-zero): the component
    carries the model, autoscaling targets inference-component/<name>

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
import time

VARIANT_DIM = "sagemaker:variant:DesiredInstanceCount"
IC_DIM = "sagemaker:inference-component:DesiredCopyCount"


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


def json_out(proc: subprocess.CompletedProcess, default):
    if proc.returncode != 0:
        return default
    try:
        return json.loads(proc.stdout) or default
    except json.JSONDecodeError:
        return default


def resolve_region(arg_region: str | None) -> str:
    """Region from arg, then env, then the active profile's config."""
    if arg_region:
        return arg_region
    for var in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if os.environ.get(var):
            return os.environ[var]
    proc = run_aws(["configure", "get", "region"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def delete_alarms(prefix: str, reg: list[str]) -> None:
    alarms = json_out(
        run_aws(["cloudwatch", "describe-alarms", "--alarm-name-prefix", prefix,
                 "--query", "MetricAlarms[*].AlarmName", "--output", "json", *reg]),
        [],
    )
    if alarms:
        run_aws(["cloudwatch", "delete-alarms", "--alarm-names", *alarms, *reg])
        log(f"Deleted alarms: {' '.join(alarms)}")


def delete_scaling_stack(resource_id: str, dimension: str, reg: list[str]) -> None:
    """Delete every scaling policy on a target, then deregister the target."""
    policies = json_out(
        run_aws(["application-autoscaling", "describe-scaling-policies",
                 "--service-namespace", "sagemaker", "--resource-id", resource_id,
                 "--query", "ScalingPolicies[*].PolicyName", "--output", "json", *reg]),
        [],
    )
    for policy in policies:
        run_aws(["application-autoscaling", "delete-scaling-policy",
                 "--service-namespace", "sagemaker", "--resource-id", resource_id,
                 "--scalable-dimension", dimension, "--policy-name", policy, *reg])
        log(f"Deleted autoscaling policy: {policy}")

    targets = json_out(
        run_aws(["application-autoscaling", "describe-scalable-targets",
                 "--service-namespace", "sagemaker", "--resource-ids", resource_id,
                 "--query", "ScalableTargets[*].ResourceId", "--output", "json", *reg]),
        [],
    )
    if resource_id in targets:
        run_aws(["application-autoscaling", "deregister-scalable-target",
                 "--service-namespace", "sagemaker", "--resource-id", resource_id,
                 "--scalable-dimension", dimension, *reg])
        log(f"Deregistered scalable target: {resource_id}")


def list_inference_components(endpoint_name: str, reg: list[str]) -> list[str]:
    return json_out(
        run_aws(["sagemaker", "list-inference-components",
                 "--endpoint-name-equals", endpoint_name,
                 "--query", "InferenceComponents[*].InferenceComponentName",
                 "--output", "json", *reg]),
        [],
    )


def component_model_name(ic_name: str, reg: list[str]) -> str:
    desc = json_out(
        run_aws(["sagemaker", "describe-inference-component",
                 "--inference-component-name", ic_name, *reg]),
        {},
    )
    return desc.get("Specification", {}).get("ModelName", "")


def delete_inference_components(ic_names: list[str], reg: list[str],
                                timeout_seconds: int = 900) -> None:
    """Delete components and wait until they are gone.

    Retries the delete on every poll, because SageMaker refuses it in two
    transient states seen in practice:
      - CREATE_IN_PROGRESS (container still starting)
      - UPDATE_RC_IN_PROGRESS (a scaling action is changing the copy count)
    An adapter component must also go before its base component, and the
    ordering falls out of the same retry loop.
    """
    pending = list(ic_names)
    deadline = time.time() + timeout_seconds
    announced: set[str] = set()
    while pending and time.time() < deadline:
        for ic_name in pending:
            if ic_name not in announced:
                log(f"Deleting inference component: {ic_name}")
                announced.add(ic_name)
            run_aws(["sagemaker", "delete-inference-component",
                     "--inference-component-name", ic_name, *reg])
        still_there = [
            ic_name for ic_name in pending
            if run_aws(["sagemaker", "describe-inference-component",
                        "--inference-component-name", ic_name, *reg]).returncode == 0
        ]
        pending = still_there
        if pending:
            time.sleep(15)

    if pending:
        log(f"WARNING: components still present after {timeout_seconds}s: {' '.join(pending)}")
    else:
        log("All inference components deleted")


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
    model_names: list[str] = []
    desc = run_aws(["sagemaker", "describe-endpoint", "--endpoint-name", endpoint_name, *reg])
    endpoint_exists = desc.returncode == 0
    if endpoint_exists:
        config_name = json_out(desc, {}).get("EndpointConfigName", "")
    else:
        log("Endpoint not found — checking for orphan resources anyway")

    if config_name:
        cfg = json_out(
            run_aws(["sagemaker", "describe-endpoint-config",
                     "--endpoint-config-name", config_name, *reg]),
            {},
        )
        # Model-based endpoints name the model on the variant. IC-based ones do not.
        for variant in cfg.get("ProductionVariants", []):
            if variant.get("ModelName"):
                model_names.append(variant["ModelName"])

    ic_names = list_inference_components(endpoint_name, reg)
    if ic_names:
        log(f"Inference components on this endpoint: {' '.join(ic_names)}")
        for ic_name in ic_names:
            model = component_model_name(ic_name, reg)
            if model and model not in model_names:
                model_names.append(model)

    # Alarms — discovered by name prefix. deploy.py / deploy_async.py name them
    # "<endpoint>-*"; deploy_ic.py names the wake alarm "<component>-*".
    delete_alarms(f"{endpoint_name}-", reg)
    for ic_name in ic_names:
        delete_alarms(f"{ic_name}-", reg)

    # Autoscaling — variant target (model-based) and component targets (IC-based).
    delete_scaling_stack(f"endpoint/{endpoint_name}/variant/AllTraffic", VARIANT_DIM, reg)
    for ic_name in ic_names:
        delete_scaling_stack(f"inference-component/{ic_name}", IC_DIM, reg)

    # Inference components must go before the endpoint.
    if ic_names:
        delete_inference_components(ic_names, reg)

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

    # Models
    for model_name in model_names:
        if run_aws(["sagemaker", "describe-model", "--model-name", model_name, *reg]).returncode == 0:
            run_aws(["sagemaker", "delete-model", "--model-name", model_name, *reg])
            log(f"Deleted model: {model_name}")

    log("Teardown complete. Data capture S3 objects (if any) NOT deleted — manage separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
