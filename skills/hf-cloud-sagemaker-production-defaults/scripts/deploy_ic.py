#!/usr/bin/env python
"""Create a real-time SageMaker endpoint that scales to ZERO instances.

Real-time scale-to-zero requires inference components. The endpoint hosts no
model directly; a component carries the model and its copy count is the thing
that scales, down to zero.

Minimal usage:
    python deploy_ic.py --model-name <name> --image-uri <uri> \
        --inference-ami-version <ami> --role-arn <arn> \
        --instance-type ml.g5.xlarge --region <region> \
        --env SM_VLLM_MODEL=Qwen/Qwen3-0.6B --env SM_VLLM_HOST=0.0.0.0

Four pieces make zero work, and all four are required:
  1. endpoint config: ManagedInstanceScaling with MinInstanceCount=0
  2. scalable target on inference-component/<name> with MinCapacity=0
  3. target-tracking policy on concurrency (handles 1..n)
  4. step-scaling policy + NoCapacityInvocationFailures alarm (handles 0 -> 1)

Target tracking alone cannot leave zero, so without (4) the endpoint scales to
zero once and never wakes.

Measured on ml.g5.xlarge with Qwen3-0.6B from the Hub (July 2026):
  endpoint InService 4 min (it starts empty) -> component InService +6 min ->
  idle scale-in to 0 copies 11 min -> 0 instances +12 min -> wake from zero
  9 min 24 s from the first rejected request to a 200.

See SKILL.md, section "Scale to zero for real-time endpoints".
"""

import argparse
import json
import sys
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from _common import (
    build_tags,
    create_model,
    log as _log,
    make_endpoint_name,
    parse_env,
    wait_for_endpoint,
)


# Defaults — change here, not at call sites.
DEFAULTS = {
    "initial_instance_count": 1,
    "min_instance_count": 0,
    "max_instance_count": 2,
    "min_copy_count": 0,
    "max_copy_count": 4,
    # Concurrent requests per copy. Target tracking scales out above this.
    "concurrency_target_per_copy": 5,
    "scale_in_cooldown_seconds": 300,
    "scale_out_cooldown_seconds": 300,
    "wake_cooldown_seconds": 60,
    "wake_step_size": 1,
    "model_data_download_timeout": 3600,
    # 3600 is the API maximum, but a crash-looping container holds the component
    # in Creating for the whole timeout. 1800 plus the log scan below surfaces a
    # broken container in about a minute instead.
    "container_startup_timeout": 1800,
    # A scheduling reservation, not a cap: the container may use more. Keep it
    # small. ml.g5.xlarge accepts 1024 and rejects 4096, far below its 16 GiB.
    "min_memory_required_mb": 1024,
    "accelerator_devices": 1,
    "alarm_evaluation_periods": 1,
    "alarm_period_seconds": 300,
    "alarm_5xx_threshold_count": 5,
    "environment_tag": "dev",
}

IC_DIMENSION = "sagemaker:inference-component:DesiredCopyCount"
# High-resolution concurrency, not invocations/minute: it reacts up to 6x faster
# and its idle zeros are what drive scale-in to zero.
CONCURRENCY_METRIC = "SageMakerInferenceComponentConcurrentRequestsPerCopyHighResolution"
WAKE_METRIC = "NoCapacityInvocationFailures"

# supervisord restarts a dying server, so the component status stays Creating.
# These markers are the only early evidence of a crash loop.
CRASH_MARKERS = (
    "exited: app",
    "not expected",
    "Worker died",
    "Load model failed",
    "ImportError",
    "Traceback (most recent call last)",
    "api_server.py: error:",
)


def log(msg: str) -> None:
    _log("deploy_ic", msg)


def create_endpoint_config(
    sm: Any, *, config_name: str, instance_type: str, role_arn: str,
    initial_instance_count: int, min_instance_count: int, max_instance_count: int,
    inference_ami_version: str | None, tags: list[dict],
) -> str:
    log(f"Creating IC endpoint config: {config_name}")

    variant: dict[str, Any] = {
        "VariantName": "AllTraffic",
        "InstanceType": instance_type,
        "InitialInstanceCount": initial_instance_count,
        "ModelDataDownloadTimeoutInSeconds": DEFAULTS["model_data_download_timeout"],
        "ContainerStartupHealthCheckTimeoutInSeconds": DEFAULTS["container_startup_timeout"],
        # MinInstanceCount=0 is what allows the endpoint to drop every instance.
        "ManagedInstanceScaling": {
            "Status": "ENABLED",
            "MinInstanceCount": min_instance_count,
            "MaxInstanceCount": max_instance_count,
        },
        "RoutingConfig": {"RoutingStrategy": "LEAST_OUTSTANDING_REQUESTS"},
    }

    # Same vLLM CUDA 13+ rule as deploy.py, and it coexists with
    # ManagedInstanceScaling on the same variant (verified).
    if inference_ami_version:
        variant["InferenceAmiVersion"] = inference_ami_version
        log(f"  InferenceAmiVersion set to: {inference_ami_version}")

    # Two differences from a model-based config: no ModelName on the variant
    # (the component carries the model) and ExecutionRoleArn moves up here.
    try:
        sm.create_endpoint_config(
            EndpointConfigName=config_name,
            ExecutionRoleArn=role_arn,
            ProductionVariants=[variant],
            Tags=tags,
        )
    except ClientError as e:
        if "Cannot create already existing endpoint configuration" in str(e):
            log(f"Endpoint config {config_name} already exists — reusing")
        else:
            raise
    return config_name


def create_endpoint(sm: Any, *, endpoint_name: str, config_name: str, tags: list[dict]) -> None:
    log(f"Creating endpoint: {endpoint_name}")
    sm.create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=config_name,
        Tags=tags,
    )


def create_inference_component(
    sm: Any, *, ic_name: str, endpoint_name: str, model_name: str,
    accelerator_devices: int, min_memory_mb: int, tags: list[dict],
) -> None:
    log(f"Creating inference component: {ic_name}")
    sm.create_inference_component(
        InferenceComponentName=ic_name,
        EndpointName=endpoint_name,
        VariantName="AllTraffic",
        Specification={
            "ModelName": model_name,
            "StartupParameters": {
                "ModelDataDownloadTimeoutInSeconds": DEFAULTS["model_data_download_timeout"],
                "ContainerStartupHealthCheckTimeoutInSeconds": DEFAULTS["container_startup_timeout"],
            },
            "ComputeResourceRequirements": {
                "MinMemoryRequiredInMb": min_memory_mb,
                "NumberOfAcceleratorDevicesRequired": accelerator_devices,
            },
        },
        RuntimeConfig={"CopyCount": 1},
        Tags=tags,
    )


def scan_component_logs(ic_name: str, region: str, limit: int = 200) -> list[str]:
    """Return crash-marker lines from the component's newest log stream.

    Returns [] when the log group does not exist yet, or when the caller cannot
    read it. A diagnostic that is unavailable never blocks the deployment.
    """
    logs = boto3.client("logs", region_name=region)
    group = f"/aws/sagemaker/InferenceComponents/{ic_name}"
    try:
        streams = logs.describe_log_streams(
            logGroupName=group, orderBy="LastEventTime", descending=True, limit=1
        )["logStreams"]
    except ClientError:
        return []
    if not streams:
        return []
    try:
        events = logs.get_log_events(
            logGroupName=group,
            logStreamName=streams[0]["logStreamName"],
            limit=limit,
            startFromHead=False,
        )["events"]
    except ClientError:
        return []
    return [
        event["message"].strip()[:500]
        for event in events
        if any(marker in event["message"] for marker in CRASH_MARKERS)
    ]


def wait_for_component(sm: Any, ic_name: str, region: str, timeout_minutes: int = 30) -> None:
    """Poll DescribeInferenceComponent until InService.

    Also scans the container log on every poll. A crash loop never changes the
    component status — it stays Creating until the startup timeout expires — so
    the log is the only early signal.
    """
    log(f"Waiting for inference component {ic_name} (up to {timeout_minutes} min)...")
    start = time.time()
    deadline = start + timeout_minutes * 60
    polls = 0

    while time.time() < deadline:
        desc = sm.describe_inference_component(InferenceComponentName=ic_name)
        status = desc["InferenceComponentStatus"]
        elapsed = int(time.time() - start)

        if status == "InService":
            log(f"Component InService after {elapsed}s")
            return
        if status == "Failed":
            reason = desc.get("FailureReason", "(no reason given)")
            raise RuntimeError(f"Inference component failed after {elapsed}s: {reason}")

        polls += 1
        log(f"  status={status} elapsed={elapsed}s")
        # One grace poll: the first seconds of any boot look noisy.
        if polls >= 2:
            hits = scan_component_logs(ic_name, region)
            if hits:
                log("Container is crash-looping. Log evidence:")
                for line in hits[-6:]:
                    log(f"  {line}")
                raise RuntimeError(
                    "Container does not stay up. Fix the container error above; "
                    "the component status alone would have hidden this for "
                    f"{DEFAULTS['container_startup_timeout']}s."
                )
        time.sleep(30)

    raise TimeoutError(f"Component did not reach InService within {timeout_minutes} minutes")


def register_autoscaling(
    *, ic_name: str, min_copies: int, max_copies: int, concurrency_target: int,
    region: str,
) -> str:
    """Register the scalable target and both policies. Returns the step ARN.

    Two policies, both required:
      1. target tracking on concurrency per copy — scales 1..n, and its idle
         zeros are what take the count down to zero
      2. step scaling — the only way out of zero, since target tracking cannot
         divide by zero copies
    """
    log(f"Registering component autoscaling: copies={min_copies}-{max_copies} "
        f"concurrency-target={concurrency_target}/copy")
    appscaling = boto3.client("application-autoscaling", region_name=region)
    resource_id = f"inference-component/{ic_name}"

    appscaling.register_scalable_target(
        ServiceNamespace="sagemaker",
        ResourceId=resource_id,
        ScalableDimension=IC_DIMENSION,
        MinCapacity=min_copies,
        MaxCapacity=max_copies,
    )
    appscaling.put_scaling_policy(
        PolicyName=f"{ic_name}-concurrency-target-tracking",
        ServiceNamespace="sagemaker",
        ResourceId=resource_id,
        ScalableDimension=IC_DIMENSION,
        PolicyType="TargetTrackingScaling",
        TargetTrackingScalingPolicyConfiguration={
            "TargetValue": float(concurrency_target),
            "PredefinedMetricSpecification": {"PredefinedMetricType": CONCURRENCY_METRIC},
            "ScaleInCooldown": DEFAULTS["scale_in_cooldown_seconds"],
            "ScaleOutCooldown": DEFAULTS["scale_out_cooldown_seconds"],
        },
    )
    resp = appscaling.put_scaling_policy(
        PolicyName=f"{ic_name}-step-wake-from-zero",
        ServiceNamespace="sagemaker",
        ResourceId=resource_id,
        ScalableDimension=IC_DIMENSION,
        PolicyType="StepScaling",
        StepScalingPolicyConfiguration={
            "AdjustmentType": "ChangeInCapacity",
            "MetricAggregationType": "Maximum",
            "Cooldown": DEFAULTS["wake_cooldown_seconds"],
            "StepAdjustments": [
                {"MetricIntervalLowerBound": 0, "ScalingAdjustment": DEFAULTS["wake_step_size"]},
            ],
        },
    )
    return resp["PolicyARN"]


def create_alarms(
    *, ic_name: str, endpoint_name: str, step_policy_arn: str,
    sns_topic_arn: str | None, region: str,
) -> None:
    """Wake alarm (drives the step policy) plus an error alarm."""
    cw = boto3.client("cloudwatch", region_name=region)

    # The wake alarm's action is the step policy, never an SNS topic. Period 30
    # with one datapoint keeps the wake latency near a minute.
    log(f"Creating wake alarm: {ic_name}-wake-from-zero")
    cw.put_metric_alarm(
        AlarmName=f"{ic_name}-wake-from-zero",
        AlarmDescription="Component invoked with zero copies — wake from zero",
        AlarmActions=[step_policy_arn],
        MetricName=WAKE_METRIC,
        Namespace="AWS/SageMaker",
        Statistic="Maximum",
        Dimensions=[{"Name": "InferenceComponentName", "Value": ic_name}],
        Period=30,
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=1,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        TreatMissingData="missing",
    )

    alarm_actions = [sns_topic_arn] if sns_topic_arn else []
    cw.put_metric_alarm(
        AlarmName=f"{endpoint_name}-Invocation5XXErrors",
        AlarmDescription="5XX errors > 5 in 5min",
        AlarmActions=alarm_actions,
        MetricName="Invocation5XXErrors",
        Namespace="AWS/SageMaker",
        Statistic="Sum",
        Dimensions=[
            {"Name": "EndpointName", "Value": endpoint_name},
            {"Name": "VariantName", "Value": "AllTraffic"},
        ],
        Period=DEFAULTS["alarm_period_seconds"],
        EvaluationPeriods=DEFAULTS["alarm_evaluation_periods"],
        Threshold=DEFAULTS["alarm_5xx_threshold_count"],
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
    )
    if not sns_topic_arn:
        log("WARNING: no --sns-alarm-topic — the error alarm won't notify anyone.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    # Required
    p.add_argument("--model-name", required=True)
    p.add_argument("--image-uri", required=True, help="From serving-image-selection")
    p.add_argument("--role-arn", required=True, help="From sagemaker-iam-preflight")
    p.add_argument("--instance-type", required=True, help="e.g. ml.g5.xlarge")
    p.add_argument("--region", required=True, help="From aws-context-discovery")

    # Conditional
    p.add_argument("--model-s3-uri", default=None,
                   help="Pre-staged weights. Strongly recommended here: they are "
                        "re-downloaded on every wake from zero.")
    p.add_argument("--env", action="append", default=[], help="KEY=VALUE; repeatable")
    p.add_argument("--inference-ami-version", default=None,
                   help="REQUIRED for vLLM DLC with CUDA 13+ "
                        "(al2-ami-sagemaker-inference-gpu-3-1)")

    # Naming
    p.add_argument("--endpoint-name", default=None, help="Default: <model-name>-<timestamp>")
    p.add_argument("--inference-component-name", default=None, help="Default: <model-name>-ic")
    p.add_argument("--project", default=None, help="Tag value (default: model name)")
    p.add_argument("--environment", default=DEFAULTS["environment_tag"])

    # Capacity
    p.add_argument("--initial-instance-count", type=int, default=DEFAULTS["initial_instance_count"])
    p.add_argument("--min-instance-count", type=int, default=DEFAULTS["min_instance_count"],
                   help="0 enables scale-to-zero. Anything else defeats the point.")
    p.add_argument("--max-instance-count", type=int, default=DEFAULTS["max_instance_count"])
    p.add_argument("--min-copy-count", type=int, default=DEFAULTS["min_copy_count"])
    p.add_argument("--max-copy-count", type=int, default=DEFAULTS["max_copy_count"])
    p.add_argument("--concurrency-target-per-copy", type=int,
                   default=DEFAULTS["concurrency_target_per_copy"])

    # Component resources
    p.add_argument("--accelerator-devices", type=int, default=DEFAULTS["accelerator_devices"],
                   help="Must match SM_VLLM_TENSOR_PARALLEL_SIZE for multi-GPU models")
    p.add_argument("--min-memory-mb", type=int, default=DEFAULTS["min_memory_required_mb"])

    # Alarms
    p.add_argument("--sns-alarm-topic", default=None, help="SNS topic ARN for the error alarm")
    p.add_argument("--no-alarms", action="store_true",
                   help="NOT RECOMMENDED: without the wake alarm the endpoint never leaves zero")
    p.add_argument("--no-autoscaling", action="store_true",
                   help="NOT RECOMMENDED: creates the endpoint without any scaling")

    args = p.parse_args()

    env_dict = parse_env(args.env)
    endpoint_name = make_endpoint_name(args.model_name, args.endpoint_name)
    config_name = f"{endpoint_name}-config"
    ic_name = args.inference_component_name or f"{args.model_name.replace('_', '-').lower()}-ic"[:63]

    sts = boto3.client("sts", region_name=args.region)
    sm = boto3.client("sagemaker", region_name=args.region)
    identity = sts.get_caller_identity()

    if args.min_instance_count != 0:
        log(f"NOTE: --min-instance-count {args.min_instance_count} — this endpoint "
            "will NOT scale to zero instances.")

    tags = build_tags(
        project=args.project or args.model_name,
        caller_arn=identity["Arn"],
        environment=args.environment,
        model_s3_uri=args.model_s3_uri,
        extra={"InferenceMode": "realtime-ic-scale-to-zero"},
    )

    create_model(
        sm, model_name=args.model_name, image_uri=args.image_uri,
        role_arn=args.role_arn, model_s3_uri=args.model_s3_uri,
        env=env_dict, tags=tags, log_prefix="deploy_ic",
    )
    create_endpoint_config(
        sm, config_name=config_name, instance_type=args.instance_type,
        role_arn=args.role_arn, initial_instance_count=args.initial_instance_count,
        min_instance_count=args.min_instance_count,
        max_instance_count=args.max_instance_count,
        inference_ami_version=args.inference_ami_version, tags=tags,
    )
    create_endpoint(sm, endpoint_name=endpoint_name, config_name=config_name, tags=tags)
    # An IC endpoint starts empty, so this is fast (~4 min): no model loads yet.
    wait_for_endpoint(sm, endpoint_name, log_prefix="deploy_ic")

    create_inference_component(
        sm, ic_name=ic_name, endpoint_name=endpoint_name, model_name=args.model_name,
        accelerator_devices=args.accelerator_devices, min_memory_mb=args.min_memory_mb,
        tags=tags,
    )
    wait_for_component(sm, ic_name, args.region)

    step_policy_arn = None
    if not args.no_autoscaling:
        step_policy_arn = register_autoscaling(
            ic_name=ic_name, min_copies=args.min_copy_count,
            max_copies=args.max_copy_count,
            concurrency_target=args.concurrency_target_per_copy, region=args.region,
        )
    else:
        log("WARNING: autoscaling skipped. This endpoint will not scale at all.")

    if not args.no_alarms and step_policy_arn:
        create_alarms(
            ic_name=ic_name, endpoint_name=endpoint_name,
            step_policy_arn=step_policy_arn, sns_topic_arn=args.sns_alarm_topic,
            region=args.region,
        )
    elif not args.no_alarms:
        log("WARNING: no step policy, so no wake alarm. Nothing wakes this endpoint.")

    # Summary
    log("")
    log(f"Deployment complete: {endpoint_name}")
    log(f"  Component:       {ic_name}")
    log(f"  Instance:        {args.instance_type} "
        f"({args.min_instance_count}-{args.max_instance_count})")
    log(f"  Copies:          {args.min_copy_count}-{args.max_copy_count}")
    log(f"  Scale to zero:   {'YES' if args.min_instance_count == 0 and args.min_copy_count == 0 else 'NO'}")
    log("")
    log("Idle behaviour: copies reach 0 after ~11 min without traffic, instances")
    log("~12 min later. The first request after that returns a 400 and wakes the")
    log("endpoint; a 200 follows about 9 min later (Hub download included).")
    log("")
    log(f"Test:     python3 invoke_endpoint.py --endpoint-name {endpoint_name} \\")
    log(f"            --inference-component-name {ic_name} \\")
    log("            --payload '{\"prompt\": \"hello\", \"max_tokens\": 16}' \\")
    log(f"            --wait-for-capacity 900 --region {args.region}")
    log(f"Teardown: python3 teardown.py {endpoint_name} {args.region}")

    print(json.dumps({
        "endpoint_name": endpoint_name,
        "endpoint_config_name": config_name,
        "model_name": args.model_name,
        "inference_component_name": ic_name,
        "step_policy_arn": step_policy_arn,
        "region": args.region,
        "instance_type": args.instance_type,
        "scales_to_zero": args.min_instance_count == 0 and args.min_copy_count == 0,
    }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
