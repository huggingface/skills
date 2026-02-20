#!/usr/bin/env python3
"""
Monitor Hugging Face Space build and runtime status with error detection.

Provides:
- Real-time build status monitoring
- Error pattern detection in logs
- Health checks for running Spaces
- Actionable fix suggestions

Usage:
    python monitor_space.py status username/my-space
    python monitor_space.py watch username/my-space
    python monitor_space.py logs username/my-space
    python monitor_space.py analyze-errors username/my-space
    python monitor_space.py health-check username/my-space
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests
from huggingface_hub import HfApi, space_info


# Common error patterns and their fixes
ERROR_PATTERNS = {
    "module_not_found": {
        "pattern": r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        "description": "Missing Python package",
        "fix_template": "Add '{match}' to requirements.txt",
        "auto_fixable": True,
    },
    "import_error": {
        "pattern": r"ImportError: cannot import name ['\"]([^'\"]+)['\"]",
        "description": "Import error - version mismatch or missing package",
        "fix_template": "Check package versions in requirements.txt. May need to pin specific version.",
        "auto_fixable": False,
    },
    "cuda_oom": {
        "pattern": r"(CUDA out of memory|OutOfMemoryError|torch\.cuda\.OutOfMemoryError)",
        "description": "GPU memory exceeded",
        "fix_template": "Model too large for hardware. Upgrade to larger GPU tier or use quantization.",
        "auto_fixable": False,
    },
    "cuda_not_available": {
        "pattern": r"(CUDA is not available|AssertionError: Torch not compiled with CUDA)",
        "description": "No GPU available but code requires it",
        "fix_template": "Set Space hardware to GPU tier (ZeroGPU, T4, L4, etc.) in Settings.",
        "auto_fixable": False,
    },
    "hf_token_invalid": {
        "pattern": r"(401|403).*(token|unauthorized|forbidden)",
        "description": "HF token invalid or missing",
        "fix_template": "Add HF_TOKEN secret in Space Settings with a valid token.",
        "auto_fixable": False,
    },
    "gradio_hffolder": {
        "pattern": r"cannot import name ['\"]HfFolder['\"]",
        "description": "Gradio/huggingface_hub version mismatch",
        "fix_template": "Use gradio>=5.0.0 and huggingface_hub>=0.26.0 in requirements.txt",
        "auto_fixable": True,
    },
    "model_not_found": {
        "pattern": r"OSError: .+ does not appear to have a file named (pytorch_model\.bin|model\.safetensors)",
        "description": "Model files not found - may be LoRA adapter",
        "fix_template": "Model appears to be a LoRA adapter. Use PEFT to load: PeftModel.from_pretrained(base_model, adapter_id)",
        "auto_fixable": False,
    },
    "chat_template_missing": {
        "pattern": r"(Cannot use chat template|Chat template is not defined)",
        "description": "Model doesn't have chat template",
        "fix_template": "Use text-generation instead of chat, or apply a chat template manually.",
        "auto_fixable": False,
    },
    "zerogpu_timeout": {
        "pattern": r"(GPU allocation timed out|Queue timeout|ZeroGPU.*timeout)",
        "description": "ZeroGPU queue timeout",
        "fix_template": "High demand on ZeroGPU. Try again later or use a paid GPU tier.",
        "auto_fixable": False,
    },
    "zerogpu_duration": {
        "pattern": r"(GPU time limit exceeded|duration.*exceeded)",
        "description": "Function exceeded ZeroGPU time limit",
        "fix_template": "Increase @spaces.GPU(duration=X) or optimize code to run faster.",
        "auto_fixable": False,
    },
    "gradio_examples_format": {
        "pattern": r"ValueError: .*(examples|must be.*(nested|list of lists))",
        "description": "Gradio 5.x examples format error",
        "fix_template": "Use nested lists for examples: [['ex1'], ['ex2']] not ['ex1', 'ex2']",
        "auto_fixable": True,
    },
    "disk_space": {
        "pattern": r"(No space left on device|OSError: \[Errno 28\])",
        "description": "Disk space exhausted",
        "fix_template": "Model too large for disk. Upgrade storage tier or use streaming.",
        "auto_fixable": False,
    },
    "gated_model": {
        "pattern": r"(Cannot access gated repo|gated.*access|401.*gated)",
        "description": "Gated model requires access",
        "fix_template": "Request access to the model on HF Hub, then add HF_TOKEN secret.",
        "auto_fixable": False,
    },
    "syntax_error": {
        "pattern": r"SyntaxError: (.+)",
        "description": "Python syntax error",
        "fix_template": "Fix syntax error in app.py: {match}",
        "auto_fixable": False,
    },
    "port_in_use": {
        "pattern": r"(Address already in use|port .* is already allocated)",
        "description": "Port conflict",
        "fix_template": "Remove explicit port binding. Gradio handles this automatically in Spaces.",
        "auto_fixable": True,
    },
}


@dataclass
class SpaceStatus:
    """Current status of a Space."""
    repo_id: str
    stage: str  # BUILDING, RUNNING, RUNTIME_ERROR, PAUSED, etc.
    hardware: Optional[str] = None
    sdk: Optional[str] = None
    error_message: Optional[str] = None
    url: Optional[str] = None


@dataclass
class DetectedError:
    """An error detected in Space logs."""
    error_type: str
    description: str
    matched_text: str
    fix_suggestion: str
    auto_fixable: bool
    match_groups: tuple = ()


def get_space_status(repo_id: str) -> SpaceStatus:
    """Get current status of a Space."""
    try:
        info = space_info(repo_id)
        runtime = info.runtime

        return SpaceStatus(
            repo_id=repo_id,
            stage=runtime.stage if runtime else "UNKNOWN",
            hardware=runtime.hardware if runtime else None,
            sdk=info.sdk,
            url=f"https://huggingface.co/spaces/{repo_id}",
        )
    except Exception as e:
        return SpaceStatus(
            repo_id=repo_id,
            stage="ERROR",
            error_message=str(e),
        )


def get_build_logs(repo_id: str, lines: int = 200) -> str:
    """
    Fetch recent build logs from a Space.

    Note: This uses the HF Spaces logs endpoint which may require authentication.
    """
    api = HfApi()

    try:
        # Try to get logs via the API
        # The logs endpoint format: https://huggingface.co/api/spaces/{repo_id}/logs/build
        token = api.token
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # Build logs endpoint
        logs_url = f"https://huggingface.co/api/spaces/{repo_id}/logs/build"
        response = requests.get(logs_url, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            return "[No build logs available yet]"
        else:
            return f"[Could not fetch logs: HTTP {response.status_code}]"

    except Exception as e:
        return f"[Error fetching logs: {e}]"


def get_runtime_logs(repo_id: str, lines: int = 200) -> str:
    """Fetch runtime logs from a running Space."""
    api = HfApi()

    try:
        token = api.token
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # Runtime logs endpoint
        logs_url = f"https://huggingface.co/api/spaces/{repo_id}/logs/run"
        response = requests.get(logs_url, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            return "[No runtime logs available]"
        else:
            return f"[Could not fetch logs: HTTP {response.status_code}]"

    except Exception as e:
        return f"[Error fetching logs: {e}]"


def detect_errors(logs: str) -> list[DetectedError]:
    """
    Parse logs to identify common error patterns.

    Returns a list of detected errors with fix suggestions.
    """
    errors = []

    for error_type, pattern_info in ERROR_PATTERNS.items():
        pattern = pattern_info["pattern"]
        matches = re.finditer(pattern, logs, re.IGNORECASE | re.MULTILINE)

        for match in matches:
            groups = match.groups()
            fix = pattern_info["fix_template"]

            # Substitute match groups into fix template
            if groups and "{match}" in fix:
                fix = fix.format(match=groups[0])

            errors.append(DetectedError(
                error_type=error_type,
                description=pattern_info["description"],
                matched_text=match.group(0)[:200],  # Truncate long matches
                fix_suggestion=fix,
                auto_fixable=pattern_info["auto_fixable"],
                match_groups=groups,
            ))

    return errors


def watch_space(repo_id: str, interval: int = 10, max_checks: int = 60):
    """
    Watch Space build status until it's running or fails.

    Args:
        repo_id: Space repository ID
        interval: Seconds between status checks
        max_checks: Maximum number of checks before timeout
    """
    print(f"\nWatching Space: {repo_id}")
    print(f"URL: https://huggingface.co/spaces/{repo_id}")
    print("-" * 50)

    previous_stage = None

    for i in range(max_checks):
        status = get_space_status(repo_id)

        if status.stage != previous_stage:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Stage: {status.stage}")

            if status.stage == "RUNNING":
                print(f"\n✅ Space is running!")
                print(f"   URL: {status.url}")
                return True

            elif status.stage in ["RUNTIME_ERROR", "BUILD_ERROR"]:
                print(f"\n❌ Space failed: {status.stage}")
                print("\nAnalyzing errors...")
                logs = get_build_logs(repo_id) + "\n" + get_runtime_logs(repo_id)
                errors = detect_errors(logs)

                if errors:
                    print_error_analysis(errors)
                else:
                    print("   No specific error patterns detected.")
                    print("   Check logs manually for more details.")
                return False

            elif status.stage == "PAUSED":
                print(f"\n⏸️  Space is paused. Restart it to continue.")
                return False

            previous_stage = status.stage

        time.sleep(interval)

    print(f"\n⚠️  Timeout after {max_checks * interval} seconds")
    print(f"   Current stage: {status.stage}")
    return False


def print_error_analysis(errors: list[DetectedError]):
    """Pretty print detected errors with fixes."""
    print(f"\n{'=' * 60}")
    print(f"DETECTED ERRORS ({len(errors)} found)")
    print("=" * 60)

    # Deduplicate by error type
    seen_types = set()
    unique_errors = []
    for error in errors:
        if error.error_type not in seen_types:
            seen_types.add(error.error_type)
            unique_errors.append(error)

    for i, error in enumerate(unique_errors, 1):
        auto_fix = "🔧 Auto-fixable" if error.auto_fixable else "📋 Manual fix"
        print(f"\n{i}. {error.description} [{auto_fix}]")
        print(f"   Type: {error.error_type}")
        print(f"   Matched: {error.matched_text[:100]}...")
        print(f"   Fix: {error.fix_suggestion}")

    print("\n" + "=" * 60)


def run_health_check(repo_id: str) -> dict:
    """
    Run comprehensive health check on a Space.

    Returns dict with check results.
    """
    results = {
        "repo_id": repo_id,
        "checks": {},
        "healthy": True,
        "issues": [],
    }

    # Check 1: Space status
    status = get_space_status(repo_id)
    results["checks"]["status"] = {
        "stage": status.stage,
        "hardware": status.hardware,
        "sdk": status.sdk,
    }

    if status.stage != "RUNNING":
        results["healthy"] = False
        results["issues"].append(f"Space is not running (stage: {status.stage})")

    # Check 2: Analyze logs for errors
    logs = get_build_logs(repo_id) + "\n" + get_runtime_logs(repo_id)
    errors = detect_errors(logs)

    results["checks"]["errors"] = {
        "count": len(errors),
        "types": list(set(e.error_type for e in errors)),
    }

    if errors:
        results["healthy"] = False
        for error in errors[:3]:  # Top 3 errors
            results["issues"].append(f"{error.description}: {error.fix_suggestion}")

    # Check 3: Try to access the Space URL
    if status.stage == "RUNNING":
        try:
            # Try to access the gradio API endpoint
            space_url = f"https://{repo_id.replace('/', '-')}.hf.space"
            response = requests.get(space_url, timeout=30)
            results["checks"]["accessibility"] = {
                "reachable": response.status_code == 200,
                "status_code": response.status_code,
            }
            if response.status_code != 200:
                results["healthy"] = False
                results["issues"].append(f"Space URL returned status {response.status_code}")
        except Exception as e:
            results["checks"]["accessibility"] = {
                "reachable": False,
                "error": str(e),
            }
            results["healthy"] = False
            results["issues"].append(f"Cannot reach Space: {e}")

    return results


def print_health_check(results: dict):
    """Pretty print health check results."""
    print(f"\n{'=' * 60}")
    print(f"HEALTH CHECK: {results['repo_id']}")
    print("=" * 60)

    # Overall status
    if results["healthy"]:
        print("\n✅ HEALTHY - Space is running normally")
    else:
        print("\n❌ UNHEALTHY - Issues detected")

    # Status check
    status = results["checks"].get("status", {})
    print(f"\nStatus:")
    print(f"  Stage: {status.get('stage', 'unknown')}")
    print(f"  Hardware: {status.get('hardware', 'unknown')}")
    print(f"  SDK: {status.get('sdk', 'unknown')}")

    # Error check
    errors = results["checks"].get("errors", {})
    print(f"\nErrors:")
    print(f"  Detected: {errors.get('count', 0)}")
    if errors.get("types"):
        print(f"  Types: {', '.join(errors['types'])}")

    # Accessibility check
    access = results["checks"].get("accessibility", {})
    if access:
        print(f"\nAccessibility:")
        print(f"  Reachable: {access.get('reachable', 'unknown')}")
        if access.get("status_code"):
            print(f"  Status code: {access['status_code']}")
        if access.get("error"):
            print(f"  Error: {access['error']}")

    # Issues
    if results["issues"]:
        print(f"\nIssues to address:")
        for i, issue in enumerate(results["issues"], 1):
            print(f"  {i}. {issue}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor HF Space build and runtime status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check current status
    python monitor_space.py status username/my-space

    # Watch build progress until complete
    python monitor_space.py watch username/my-space

    # Get build logs
    python monitor_space.py logs username/my-space --type build

    # Get runtime logs
    python monitor_space.py logs username/my-space --type runtime

    # Analyze logs for errors
    python monitor_space.py analyze-errors username/my-space

    # Run full health check
    python monitor_space.py health-check username/my-space
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status command
    status_parser = subparsers.add_parser("status", help="Get current Space status")
    status_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    # watch command
    watch_parser = subparsers.add_parser("watch", help="Watch build progress")
    watch_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    watch_parser.add_argument("--interval", type=int, default=10, help="Check interval in seconds")
    watch_parser.add_argument("--max-checks", type=int, default=60, help="Max number of checks")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Get Space logs")
    logs_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    logs_parser.add_argument("--type", choices=["build", "runtime", "both"], default="both",
                            help="Type of logs to fetch")
    logs_parser.add_argument("--lines", type=int, default=200, help="Number of lines")

    # analyze-errors command
    analyze_parser = subparsers.add_parser("analyze-errors", help="Analyze logs for errors")
    analyze_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    # health-check command
    health_parser = subparsers.add_parser("health-check", help="Run comprehensive health check")
    health_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    args = parser.parse_args()

    if args.command == "status":
        status = get_space_status(args.repo_id)
        print(f"\nSpace: {status.repo_id}")
        print(f"Stage: {status.stage}")
        print(f"Hardware: {status.hardware or 'unknown'}")
        print(f"SDK: {status.sdk or 'unknown'}")
        print(f"URL: {status.url}")
        if status.error_message:
            print(f"Error: {status.error_message}")

    elif args.command == "watch":
        success = watch_space(args.repo_id, args.interval, args.max_checks)
        sys.exit(0 if success else 1)

    elif args.command == "logs":
        if args.type in ["build", "both"]:
            print("=== BUILD LOGS ===")
            print(get_build_logs(args.repo_id, args.lines))
        if args.type in ["runtime", "both"]:
            print("\n=== RUNTIME LOGS ===")
            print(get_runtime_logs(args.repo_id, args.lines))

    elif args.command == "analyze-errors":
        print(f"Fetching logs for {args.repo_id}...")
        logs = get_build_logs(args.repo_id) + "\n" + get_runtime_logs(args.repo_id)
        errors = detect_errors(logs)

        if errors:
            print_error_analysis(errors)
        else:
            print("\n✅ No common error patterns detected in logs.")
            print("   If issues persist, check logs manually.")

    elif args.command == "health-check":
        results = run_health_check(args.repo_id)
        print_health_check(results)
        sys.exit(0 if results["healthy"] else 1)


if __name__ == "__main__":
    main()
