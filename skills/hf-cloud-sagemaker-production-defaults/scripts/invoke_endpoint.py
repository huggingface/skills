#!/usr/bin/env python3
"""Invoke a real-time SageMaker endpoint with a JSON payload. Cross-platform.

This is the BOM-safe way to test an endpoint. On Windows, writing a payload with
PowerShell's `Set-Content -Encoding UTF8` can prepend a UTF-8 byte-order mark
(BOM). SageMaker's JSON parser rejects it with:

    Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)

This helper never produces that error: it reads the payload with `utf-8-sig`
(stripping any BOM the source file may already have) and writes the request body
as plain BOM-free UTF-8 before calling `aws sagemaker-runtime invoke-endpoint`.

Usage:
    python invoke_endpoint.py --endpoint-name NAME --payload '{"inputs": "hi"}'
    python invoke_endpoint.py --endpoint-name NAME --payload-file body.json
    python invoke_endpoint.py --endpoint-name NAME --payload-file img.json \\
        --content-type application/json --region eu-west-1

Inference-component endpoints (including scale-to-zero deployments) need the
component name, and a cold endpoint needs a wait:

    python invoke_endpoint.py --endpoint-name NAME \\
        --inference-component-name COMP --payload '{"prompt": "hi"}' \\
        --wait-for-capacity 900

A component scaled to zero copies answers the first request with a 400
ValidationError ("has no capacity"). That error is also the wake signal: it
publishes NoCapacityInvocationFailures, which triggers the step-scaling policy.
With --wait-for-capacity the helper keeps retrying until a copy is in service.

The endpoint response body is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

NO_CAPACITY_MARKERS = ("has no capacity", "NoCapacity")


def log(msg: str) -> None:
    print(f"[invoke] {msg}", file=sys.stderr, flush=True)


def aws_bin() -> str:
    exe = shutil.which("aws")
    if not exe:
        log("ERROR: the 'aws' CLI was not found on PATH. Install AWS CLI v2.")
        sys.exit(2)
    return exe


def resolve_region(arg_region: str | None) -> str:
    if arg_region:
        return arg_region
    for var in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if os.environ.get(var):
            return os.environ[var]
    proc = subprocess.run(
        [aws_bin(), "configure", "get", "region"], capture_output=True, text=True
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def load_payload(args: argparse.Namespace) -> str:
    """Return the raw payload text, BOM stripped. Validates JSON when applicable."""
    if args.payload_file:
        # utf-8-sig decodes and discards a leading BOM if the file has one.
        raw = open(args.payload_file, "r", encoding="utf-8-sig").read()
    else:
        raw = args.payload

    # If it's meant to be JSON, validate and re-serialize so the body is clean.
    if "json" in args.content_type:
        try:
            return json.dumps(json.loads(raw))
        except json.JSONDecodeError as e:
            log(f"ERROR: payload is not valid JSON: {e}")
            sys.exit(1)
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region")
    parser.add_argument("--content-type", default="application/json")
    parser.add_argument(
        "--inference-component-name",
        help="Required when the endpoint hosts inference components",
    )
    parser.add_argument(
        "--wait-for-capacity", type=int, default=0, metavar="SECONDS",
        help=(
            "Retry while the component reports no capacity (scale-to-zero wake). "
            "0 fails immediately."
        ),
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--payload", help="Inline request body (e.g. a JSON string)")
    src.add_argument("--payload-file", help="Path to a file containing the request body")
    args = parser.parse_args()

    region = resolve_region(args.region)
    if not region:
        log("ERROR: no AWS region. Pass --region or set AWS_REGION.")
        return 1

    body = load_payload(args)

    # Write the request body as BOM-free UTF-8. NamedTemporaryFile + explicit
    # utf-8 encoding guarantees no BOM regardless of platform.
    body_path = None
    out_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", encoding="utf-8", delete=False
        ) as f:
            f.write(body)
            body_path = f.name
        out_fd, out_path = tempfile.mkstemp(suffix=".out")
        os.close(out_fd)

        cmd = [
            aws_bin(), "sagemaker-runtime", "invoke-endpoint",
            "--endpoint-name", args.endpoint_name,
            "--content-type", args.content_type,
            "--body", f"fileb://{body_path}",
            "--region", region,
        ]
        if args.inference_component_name:
            cmd += ["--inference-component-name", args.inference_component_name]
        cmd.append(out_path)

        log(f"Invoking {args.endpoint_name} in {region}...")
        deadline = time.time() + args.wait_for_capacity
        attempt = 0
        while True:
            attempt += 1
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                break

            err = proc.stderr.strip()
            no_capacity = any(marker in err for marker in NO_CAPACITY_MARKERS)
            if no_capacity and time.time() < deadline:
                if attempt == 1:
                    log("No capacity: the component is at zero copies. "
                        "This request triggered the wake alarm; retrying.")
                log(f"  attempt {attempt}: still no capacity, waiting 30s "
                    f"({int(deadline - time.time())}s left)")
                time.sleep(30)
                continue

            log("Invocation failed:")
            log(err)
            if no_capacity:
                log("HINT: the component has no copies in service. Pass "
                    "--wait-for-capacity 900 to wait for the wake-from-zero policy.")
            return 1

        # The response body landed in out_path; print it to stdout.
        print(open(out_path, "r", encoding="utf-8-sig").read())
        return 0
    finally:
        for p in (body_path, out_path):
            if p and os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    sys.exit(main())
