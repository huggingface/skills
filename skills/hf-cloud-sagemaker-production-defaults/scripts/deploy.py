#!/usr/bin/env python
"""Create a SageMaker real-time endpoint with production defaults.

Minimal usage:
    python deploy.py --model-name <name> --image-uri <uri> \
        --inference-ami-version <ami> --role-arn <arn> \
        --instance-type ml.g5.xlarge --region <region>

See the SKILL.md for full flags and the recommended chained-with-resolver pattern.
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
# Reasoning lives in references/deployment-template.md.
DEFAULTS = {
    "initial_instance_count": 1,
    "min_capacity": 1,
    "max_capacity": 4,
    "target_invocations_per_instance": 20,
    "scale_in_cooldown_seconds": 300,
    "scale_out_cooldown_seconds": 60,
    "data_capture_sampling_percent": 100,
    "alarm_latency_threshold_ms": 30_000,
    "alarm_5xx_threshold_count": 5,
    "alarm_overhead_threshold_ms": 2_000,
    "alarm_evaluation_periods": 1,
    "alarm_period_seconds": 300,
    "environment_tag": "dev",
}


def log(msg: str) -> None:
    _log("deploy", msg)


def create_endpoint_config(
    sm: Any, *, config_name: str, model_name: str, instance_type: str,
    initial_instance_count: int, inference_ami_version: str | None,
    data_capture_enabled: bool, data_capture_s3_uri: str | None,
    tags: list[dict],
) -> str:
    log(f"Creating endpoint config: {config_name}")

    production_variant: dict[str, Any] = {
        "VariantName": "AllTraffic",
        "ModelName": model_name,
        "InstanceType": instance_type,
        "InitialInstanceCount": initial_instance_count,
        "InitialVariantWeight": 1.0,
    }

    # InferenceAmiVersion required for vLLM DLC with CUDA 13+. Without it the
    # container dies on startup with no logs. See hf-cloud-serving-image-selection skill.
    if inference_ami_version:
        production_variant["InferenceAmiVersion"] = inference_ami_version
        log(f"  InferenceAmiVersion set to: {inference_ami_version}")

    kwargs: dict[str, Any] = {
        "EndpointConfigName": config_name,
        "ProductionVariants": [production_variant],
        "Tags": tags,
    }

    if data_capture_enabled:
        if not data_capture_s3_uri:
            raise ValueError("data_capture_enabled but no data_capture_s3_uri provided")
        kwargs["DataCaptureConfig"] = {
            "EnableCapture": True,
            "InitialSamplingPercentage": DEFAULTS["data_capture_sampling_percent"],
            "DestinationS3Uri": data_capture_s3_uri,
            "CaptureOptions": [{"CaptureMode": "Input"}, {"CaptureMode": "Output"}],
            "CaptureContentTypeHeader": {"JsonContentTypes": ["application/json"]},
        }

    try:
        sm.create_endpoint_config(**kwargs)
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


def register_autoscaling(
    *, endpoint_name: str, variant_name: str, min_capacity: int, max_capacity: int,
    target_invocations: int, scale_in_cooldown: int, scale_out_cooldown: int, region: str,
) -> None:
    log(f"Registering autoscaling: min={min_capacity} max={max_capacity} target={target_invocations}/min")
    appscaling = boto3.client("application-autoscaling", region_name=region)
    resource_id = f"endpoint/{endpoint_name}/variant/{variant_name}"

    appscaling.register_scalable_target(
        ServiceNamespace="sagemaker",
        ResourceId=resource_id,
        ScalableDimension="sagemaker:variant:DesiredInstanceCount",
        MinCapacity=min_capacity,
        MaxCapacity=max_capacity,
    )
    appscaling.put_scaling_policy(
        PolicyName=f"{endpoint_name}-target-tracking",
        ServiceNamespace="sagemaker",
        ResourceId=resource_id,
        ScalableDimension="sagemaker:variant:DesiredInstanceCount",
        PolicyType="TargetTrackingScaling",
        TargetTrackingScalingPolicyConfiguration={
            "TargetValue": float(target_invocations),
            "PredefinedMetricSpecification": {
                "PredefinedMetricType": "SageMakerVariantInvocationsPerInstance",
            },
            "ScaleInCooldown": scale_in_cooldown,
            "ScaleOutCooldown": scale_out_cooldown,
        },
    )


def create_alarms(*, endpoint_name: str, variant_name: str, sns_topic_arn: str | None, region: str) -> None:
    log(f"Creating CloudWatch alarms for {endpoint_name}")
    cw = boto3.client("cloudwatch", region_name=region)
    actions = [sns_topic_arn] if sns_topic_arn else []
    common_dims = [
        {"Name": "EndpointName", "Value": endpoint_name},
        {"Name": "VariantName", "Value": variant_name},
    ]

    alarms = [
        {
            "AlarmName": f"{endpoint_name}-ModelLatencyP99",
            "MetricName": "ModelLatency",
            "ExtendedStatistic": "p99",
            "Threshold": DEFAULTS["alarm_latency_threshold_ms"] * 1000,  # microseconds
            "ComparisonOperator": "GreaterThanThreshold",
            "AlarmDescription": "Model inference latency p99 > 30s",
        },
        {
            "AlarmName": f"{endpoint_name}-Invocation5XXErrors",
            "MetricName": "Invocation5XXErrors",
            "Statistic": "Sum",
            "Threshold": DEFAULTS["alarm_5xx_threshold_count"],
            "ComparisonOperator": "GreaterThanThreshold",
            "AlarmDescription": "5XX errors > 5 in 5min",
        },
        {
            "AlarmName": f"{endpoint_name}-OverheadLatencyP99",
            "MetricName": "OverheadLatency",
            "ExtendedStatistic": "p99",
            "Threshold": DEFAULTS["alarm_overhead_threshold_ms"] * 1000,
            "ComparisonOperator": "GreaterThanThreshold",
            "AlarmDescription": "Platform overhead latency p99 > 2s",
        },
    ]

    for spec in alarms:
        params = {
            "AlarmName": spec["AlarmName"],
            "AlarmDescription": spec["AlarmDescription"],
            "MetricName": spec["MetricName"],
            "Namespace": "AWS/SageMaker",
            "Dimensions": common_dims,
            "Period": DEFAULTS["alarm_period_seconds"],
            "EvaluationPeriods": DEFAULTS["alarm_evaluation_periods"],
            "Threshold": spec["Threshold"],
            "ComparisonOperator": spec["ComparisonOperator"],
            "TreatMissingData": "notBreaching",
            "AlarmActions": actions,
        }
        if "Statistic" in spec:
            params["Statistic"] = spec["Statistic"]
        if "ExtendedStatistic" in spec:
            params["ExtendedStatistic"] = spec["ExtendedStatistic"]
        cw.put_metric_alarm(**params)

    if not sns_topic_arn:
        log("WARNING: no --sns-alarm-topic — alarms exist but won't notify anyone.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    # Required
    p.add_argument("--model-name", required=True)
    p.add_argument("--image-uri", required=True, help="From hf-cloud-serving-image-selection")
    p.add_argument("--role-arn", required=True, help="From hf-cloud-sagemaker-iam-preflight")
    p.add_argument("--instance-type", required=True, help="e.g. ml.g5.xlarge")
    p.add_argument("--region", required=True, help="From hf-cloud-aws-context-discovery")

    # Conditional
    p.add_argument("--model-s3-uri", default=None, help="Omit when loading from HF Hub")
    p.add_argument("--env", action="append", default=[], help="KEY=VALUE; repeatable")
    p.add_argument(
        "--inference-ami-version", default=None,
        help=(
            "REQUIRED for vLLM DLC with CUDA 13+ (e.g. al2-ami-sagemaker-inference-gpu-3-1). "
            "Without this, container dies on startup with no logs. "
            "See hf-cloud-serving-image-selection's 'vLLM AMI requirement' table to map a tag to the AMI version."
        ),
    )

    # Naming
    p.add_argument("--endpoint-name", default=None, help="Default: <model-name>-<timestamp>")
    p.add_argument("--project", default=None, help="Tag value (default: model name)")
    p.add_argument("--environment", default=DEFAULTS["environment_tag"])

    # Capacity / scaling
    p.add_argument("--initial-instance-count", type=int, default=DEFAULTS["initial_instance_count"])
    p.add_argument("--min-capacity", type=int, default=DEFAULTS["min_capacity"])
    p.add_argument("--max-capacity", type=int, default=DEFAULTS["max_capacity"])
    p.add_argument("--target-invocations-per-instance", type=int, default=DEFAULTS["target_invocations_per_instance"])
    p.add_argument("--no-autoscaling", action="store_true", help="NOT RECOMMENDED")

    # Data capture (off by default)
    p.add_argument("--enable-data-capture", action="store_true", help="Log requests/responses to S3")
    p.add_argument("--data-capture-s3-uri", default=None)

    # Alarms
    p.add_argument("--sns-alarm-topic", default=None, help="SNS topic ARN for alarm notifications")
    p.add_argument("--no-alarms", action="store_true")

    args = p.parse_args()

    env_dict = parse_env(args.env)
    endpoint_name = make_endpoint_name(args.model_name, args.endpoint_name)
    config_name = f"{endpoint_name}-config"

    sts = boto3.client("sts", region_name=args.region)
    sm = boto3.client("sagemaker", region_name=args.region)
    caller_arn = sts.get_caller_identity()["Arn"]
    account_id = sts.get_caller_identity()["Account"]

    if args.enable_data_capture and not args.data_capture_s3_uri:
        args.data_capture_s3_uri = f"s3://sagemaker-{args.region}-{account_id}/{endpoint_name}/data-capture/"
        log(f"Data capture URI defaulted to: {args.data_capture_s3_uri}")

    tags = build_tags(
        project=args.project or args.model_name,
        caller_arn=caller_arn,
        environment=args.environment,
        model_s3_uri=args.model_s3_uri,
    )

    create_model(
        sm, model_name=args.model_name, image_uri=args.image_uri,
        role_arn=args.role_arn, model_s3_uri=args.model_s3_uri,
        env=env_dict, tags=tags, log_prefix="deploy",
    )
    create_endpoint_config(
        sm, config_name=config_name, model_name=args.model_name,
        instance_type=args.instance_type, initial_instance_count=args.initial_instance_count,
        inference_ami_version=args.inference_ami_version,
        data_capture_enabled=args.enable_data_capture,
        data_capture_s3_uri=args.data_capture_s3_uri, tags=tags,
    )
    create_endpoint(sm, endpoint_name=endpoint_name, config_name=config_name, tags=tags)
    wait_for_endpoint(sm, endpoint_name, log_prefix="deploy")

    if not args.no_autoscaling:
        register_autoscaling(
            endpoint_name=endpoint_name, variant_name="AllTraffic",
            min_capacity=args.min_capacity, max_capacity=args.max_capacity,
            target_invocations=args.target_invocations_per_instance,
            scale_in_cooldown=DEFAULTS["scale_in_cooldown_seconds"],
            scale_out_cooldown=DEFAULTS["scale_out_cooldown_seconds"],
            region=args.region,
        )
    else:
        log("WARNING: autoscaling skipped. Endpoint won't scale with traffic.")

    if not args.no_alarms:
        create_alarms(
            endpoint_name=endpoint_name, variant_name="AllTraffic",
            sns_topic_arn=args.sns_alarm_topic, region=args.region,
        )

    # Summary
    log("")
    log(f"Deployment complete: {endpoint_name}")
    log(f"  Instance:        {args.instance_type}")
    log(f"  Autoscaling:     {'OFF' if args.no_autoscaling else f'{args.min_capacity}-{args.max_capacity} instances'}")
    log(f"  Data capture:    {args.data_capture_s3_uri if args.enable_data_capture else 'OFF (pass --enable-data-capture)'}")
    log("")
    log(f"Test:     python3 invoke_endpoint.py --endpoint-name {endpoint_name} \\")
    log(f"            --payload '{{\"prompt\": \"hello\"}}' --region {args.region}")
    log("          (BOM-safe + cross-platform; use 'python' on Windows)")
    log(f"Teardown: python3 teardown.py {endpoint_name} {args.region}")

    # Machine-readable summary for downstream scripting
    print(json.dumps({
        "endpoint_name": endpoint_name,
        "endpoint_config_name": config_name,
        "model_name": args.model_name,
        "region": args.region,
        "instance_type": args.instance_type,
    }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
