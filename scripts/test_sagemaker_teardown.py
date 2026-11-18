#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import io
import json
import runpy
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

TEARDOWN = (
    Path(__file__).resolve().parents[1]
    / "skills/hf-cloud-sagemaker-production-defaults/scripts/teardown.py"
)


def alarm(name, **dimensions):
    return {
        "AlarmName": name,
        "Dimensions": [{"Name": key, "Value": value} for key, value in dimensions.items()],
    }


class SageMakerTeardownTest(unittest.TestCase):
    def tear_down_endpoint(self, alarms, components=()):
        main = runpy.run_path(str(TEARDOWN))["main"]
        deleted = []

        def aws(args):
            service, operation = args[:2]
            payload = []
            if (service, operation) == ("cloudwatch", "describe-alarms"):
                prefix = args[args.index("--alarm-name-prefix") + 1]
                matches = [item for item in alarms if item["AlarmName"].startswith(prefix)]
                if "--query" in args:
                    self.assertEqual(args[args.index("--query") + 1], "MetricAlarms[*].AlarmName")
                    payload = [item["AlarmName"] for item in matches]
                else:
                    payload = {"MetricAlarms": matches}
            elif (service, operation) == ("cloudwatch", "delete-alarms"):
                deleted.append(args[3:args.index("--region")])
            elif operation == "list-inference-components":
                payload = components
            elif operation.startswith("describe-"):
                return subprocess.CompletedProcess(args, 1, stdout="")
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload))

        with (
            patch.dict(main.__globals__, {"run_aws": aws}),
            patch.object(sys, "argv", [str(TEARDOWN), "llm", "us-east-1"]),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        return deleted

    def test_only_alarms_for_the_exact_endpoint(self):
        alarms = [
            alarm("llm-ModelLatency", EndpointName="llm", VariantName="AllTraffic"),
            alarm("llm-ApproximateBacklogSize", EndpointName="llm"),
            alarm("llm-prod-ModelLatency", EndpointName="llm-prod"),
            alarm("llm-wake-from-zero", InferenceComponentName="llm"),
            alarm("llm-Mismatched", EndpointName="llm-prod", InferenceComponentName="llm"),
            {"AlarmName": "llm-Unattributed"},
            {"AlarmName": "llm-NullDimensions", "Dimensions": None},
            alarm("other-Latency", EndpointName="llm"),
        ]
        self.assertEqual(
            self.tear_down_endpoint(alarms),
            [["llm-ModelLatency", "llm-ApproximateBacklogSize"]],
        )

    def test_endpoint_and_component_alarms_have_separate_scopes(self):
        alarms = [
            alarm("llm-Invocation5XXErrors", EndpointName="llm", VariantName="AllTraffic"),
            alarm("llm-worker-wake-from-zero", InferenceComponentName="llm-worker"),
            alarm("llm-worker-prod-wake-from-zero", InferenceComponentName="llm-worker-prod"),
            alarm("llm-worker-ModelLatency", EndpointName="llm-worker"),
        ]
        self.assertEqual(
            self.tear_down_endpoint(alarms, components=["llm-worker"]),
            [["llm-Invocation5XXErrors"], ["llm-worker-wake-from-zero"]],
        )

    def test_skips_delete_when_no_dimensions_match(self):
        alarms = [alarm("llm-prod-ModelLatency", EndpointName="llm-prod")]
        self.assertEqual(self.tear_down_endpoint(alarms), [])


if __name__ == "__main__":
    unittest.main()
