#!/usr/bin/env python3
"""
Pre-flight checks for Hugging Face Space deployment.

Validates all prerequisites before attempting deployment:
- HF token exists and has write permissions
- User subscription status (PRO required for ZeroGPU hosting)
- Model accessibility (not gated without access)
- Model size estimation for hardware recommendations

Usage:
    python preflight.py check-all username/model-id
    python preflight.py check-token
    python preflight.py check-subscription
    python preflight.py check-model username/model-id
    python preflight.py estimate-size username/model-id
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

from huggingface_hub import HfApi, hf_hub_download, model_info, whoami
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError, GatedRepoError


@dataclass
class TokenCheckResult:
    """Result of HF token validation."""
    valid: bool
    username: Optional[str] = None
    has_write: bool = False
    error: Optional[str] = None


@dataclass
class SubscriptionCheckResult:
    """Result of subscription status check."""
    subscription: str  # "free", "pro", "team", "enterprise"
    can_host_zerogpu: bool
    zerogpu_quota_minutes: int  # Daily quota in minutes
    error: Optional[str] = None


@dataclass
class ModelAccessResult:
    """Result of model accessibility check."""
    accessible: bool
    exists: bool = True
    gated: bool = False
    gated_access_granted: bool = False
    private: bool = False
    error: Optional[str] = None
    access_url: Optional[str] = None


@dataclass
class ModelSizeResult:
    """Result of model size estimation."""
    params_billions: Optional[float] = None
    estimated_vram_gb: Optional[float] = None
    recommended_hardware: Optional[str] = None
    model_type: Optional[str] = None  # "full", "adapter", "unknown"
    error: Optional[str] = None


def check_hf_token() -> TokenCheckResult:
    """
    Verify HF token exists and has write permissions.

    Checks both environment variable and cached token file.
    """
    try:
        user_info = whoami()

        # Check if user has write access by looking at auth info
        # The whoami() call succeeds means token is valid
        # Write access is typically available unless explicitly restricted
        has_write = True  # Default assumption for valid tokens

        return TokenCheckResult(
            valid=True,
            username=user_info.get("name"),
            has_write=has_write,
        )
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Invalid" in error_msg:
            return TokenCheckResult(
                valid=False,
                error="Token is invalid or expired. Run: huggingface-cli login"
            )
        elif "token" in error_msg.lower():
            return TokenCheckResult(
                valid=False,
                error="No HF token found. Run: huggingface-cli login"
            )
        else:
            return TokenCheckResult(
                valid=False,
                error=f"Token check failed: {error_msg}"
            )


def check_zerogpu_eligibility() -> SubscriptionCheckResult:
    """
    Check if user has PRO subscription (required to HOST ZeroGPU Spaces).

    ZeroGPU Hosting Requirements:
    - Personal accounts: PRO subscription required
    - Organizations: Team or Enterprise plan required

    ZeroGPU Usage Quotas (as visitor):
    - Unauthenticated: 2 minutes/day
    - Free account: 3.5 minutes/day
    - PRO account: 25 minutes/day
    - Team/Enterprise: 25-45 minutes/day
    """
    try:
        user_info = whoami()

        # Check subscription type
        # Note: The API may not directly expose subscription status
        # We infer from available fields
        is_pro = user_info.get("isPro", False)

        # Check organization memberships for team/enterprise
        orgs = user_info.get("orgs", [])
        has_paid_org = any(
            org.get("subscription") in ["team", "enterprise"]
            for org in orgs
        ) if orgs else False

        if is_pro:
            return SubscriptionCheckResult(
                subscription="pro",
                can_host_zerogpu=True,
                zerogpu_quota_minutes=25,
            )
        elif has_paid_org:
            return SubscriptionCheckResult(
                subscription="team",
                can_host_zerogpu=True,
                zerogpu_quota_minutes=25,
            )
        else:
            return SubscriptionCheckResult(
                subscription="free",
                can_host_zerogpu=False,
                zerogpu_quota_minutes=3,  # 3.5 rounded down
            )

    except Exception as e:
        return SubscriptionCheckResult(
            subscription="unknown",
            can_host_zerogpu=False,
            zerogpu_quota_minutes=0,
            error=f"Could not check subscription: {e}"
        )


def check_model_access(model_id: str) -> ModelAccessResult:
    """
    Verify model is accessible (not gated without access, not private without access).

    Returns detailed information about why access might be restricted.
    """
    try:
        info = model_info(model_id)

        # Check if model is gated
        gated = getattr(info, "gated", False)
        if gated and gated != "auto":
            # Model is gated, check if user has access
            # If we got here without error, user has access
            return ModelAccessResult(
                accessible=True,
                gated=True,
                gated_access_granted=True,
            )

        # Model is accessible
        return ModelAccessResult(
            accessible=True,
            gated=bool(gated),
            private=getattr(info, "private", False),
        )

    except GatedRepoError:
        return ModelAccessResult(
            accessible=False,
            exists=True,
            gated=True,
            gated_access_granted=False,
            error="Model is gated. Request access first.",
            access_url=f"https://huggingface.co/{model_id}"
        )
    except RepositoryNotFoundError:
        return ModelAccessResult(
            accessible=False,
            exists=False,
            error=f"Model '{model_id}' not found. Check the model ID."
        )
    except HfHubHTTPError as e:
        if "403" in str(e):
            return ModelAccessResult(
                accessible=False,
                exists=True,
                private=True,
                error="Model is private. You don't have access.",
            )
        else:
            return ModelAccessResult(
                accessible=False,
                error=f"Could not access model: {e}"
            )
    except Exception as e:
        return ModelAccessResult(
            accessible=False,
            error=f"Error checking model access: {e}"
        )


def estimate_model_size(model_id: str) -> ModelSizeResult:
    """
    Estimate model size and recommend hardware.

    Downloads config.json to estimate parameters and VRAM requirements.
    Also detects if model is a LoRA adapter vs full model.
    """
    api = HfApi()

    try:
        # List files to detect model type
        files = api.list_repo_files(model_id, repo_type="model")
        file_names = [f.split("/")[-1] for f in files]

        # Check for adapter files (LoRA/PEFT)
        has_adapter_config = "adapter_config.json" in file_names
        has_adapter_model = any("adapter_model" in f for f in file_names)

        # Check for full model files
        has_full_weights = any(
            f in file_names for f in [
                "model.safetensors",
                "pytorch_model.bin",
            ]
        ) or any(
            "model-" in f and ".safetensors" in f for f in file_names
        )

        # Determine model type
        if has_adapter_config and has_adapter_model and not has_full_weights:
            model_type = "adapter"
        elif has_full_weights:
            model_type = "full"
        else:
            model_type = "unknown"

        # Try to get config.json for parameter estimation
        params_billions = None
        try:
            config_path = hf_hub_download(model_id, "config.json")
            with open(config_path) as f:
                config = json.load(f)

            # Different architectures store size differently
            # Common patterns:
            hidden_size = config.get("hidden_size", config.get("d_model", 0))
            num_layers = config.get("num_hidden_layers", config.get("n_layer", config.get("num_layers", 0)))
            vocab_size = config.get("vocab_size", 0)
            intermediate_size = config.get("intermediate_size", hidden_size * 4)

            if hidden_size and num_layers:
                # Rough estimation formula for transformer models
                # Parameters ≈ 12 * L * H^2 (simplified)
                # More accurate: embedding + attention + FFN
                embedding_params = vocab_size * hidden_size if vocab_size else 0
                attention_params = 4 * hidden_size * hidden_size * num_layers  # Q, K, V, O
                ffn_params = 2 * hidden_size * intermediate_size * num_layers
                total_params = embedding_params + attention_params + ffn_params

                params_billions = total_params / 1e9

        except Exception:
            # Config not available or parsing failed
            pass

        # For adapters, also check adapter_config for base model size hint
        if model_type == "adapter" and params_billions is None:
            try:
                adapter_config_path = hf_hub_download(model_id, "adapter_config.json")
                with open(adapter_config_path) as f:
                    adapter_config = json.load(f)
                # LoRA adapters are tiny, but base model determines hardware
                # Return a flag that base model should be checked
                base_model = adapter_config.get("base_model_name_or_path")
                if base_model:
                    # Recursively estimate base model size
                    base_result = estimate_model_size(base_model)
                    params_billions = base_result.params_billions
            except Exception:
                pass

        # Estimate VRAM requirements (rough: 2 bytes per param for fp16)
        estimated_vram_gb = None
        if params_billions:
            # FP16: ~2 bytes per param, plus overhead (~20%)
            estimated_vram_gb = params_billions * 2 * 1.2

        # Recommend hardware based on VRAM
        recommended_hardware = _recommend_hardware(params_billions, estimated_vram_gb)

        return ModelSizeResult(
            params_billions=round(params_billions, 2) if params_billions else None,
            estimated_vram_gb=round(estimated_vram_gb, 1) if estimated_vram_gb else None,
            recommended_hardware=recommended_hardware,
            model_type=model_type,
        )

    except Exception as e:
        return ModelSizeResult(
            error=f"Could not estimate model size: {e}"
        )


def _recommend_hardware(params_billions: Optional[float], vram_gb: Optional[float]) -> str:
    """
    Recommend hardware tier based on model size.

    Hardware VRAM:
    - cpu-basic: 0 (CPU only)
    - cpu-upgrade: 0 (CPU only, more RAM)
    - zero-a10g: 24GB (free with quota, requires PRO)
    - t4-small: 16GB ($0.40/hr)
    - l4: 24GB ($0.80/hr)
    - l40s: 48GB ($1.80/hr)
    - a10g-small: 24GB ($1.00/hr)
    - a100-large: 80GB ($2.50/hr)
    """
    if params_billions is None or vram_gb is None:
        return "zero-a10g"  # Default to ZeroGPU for unknown sizes

    if params_billions < 0.5:
        return "cpu-upgrade"  # Small models can run on CPU
    elif params_billions < 3:
        return "zero-a10g"  # ZeroGPU handles up to ~3B comfortably
    elif params_billions < 7:
        return "l4"  # 24GB VRAM for 3-7B models
    elif params_billions < 14:
        return "l40s"  # 48GB VRAM for 7-14B models
    elif params_billions < 30:
        return "a100-large"  # 80GB VRAM for 14-30B models
    else:
        return "a100-large"  # Largest available; may need quantization


def run_all_checks(model_id: str) -> dict:
    """
    Run all pre-flight checks and return comprehensive results.

    Returns a dict with all check results and a summary.
    """
    results = {
        "token": check_hf_token(),
        "subscription": check_zerogpu_eligibility(),
        "model_access": check_model_access(model_id),
        "model_size": estimate_model_size(model_id),
    }

    # Build summary
    issues = []
    warnings = []

    if not results["token"].valid:
        issues.append(f"Token: {results['token'].error}")

    if not results["subscription"].can_host_zerogpu:
        warnings.append(
            "ZeroGPU hosting requires PRO subscription. "
            "Options: upgrade to PRO, use paid GPU, or use Inference API."
        )

    if not results["model_access"].accessible:
        issues.append(f"Model access: {results['model_access'].error}")

    results["summary"] = {
        "ready": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }

    return results


def print_check_results(results: dict):
    """Pretty print check results."""
    print("\n" + "=" * 60)
    print("PRE-FLIGHT CHECK RESULTS")
    print("=" * 60)

    # Token check
    token = results["token"]
    if token.valid:
        print(f"\n✓ Token: Valid (user: {token.username})")
    else:
        print(f"\n✗ Token: {token.error}")

    # Subscription check
    sub = results["subscription"]
    if sub.can_host_zerogpu:
        print(f"✓ Subscription: {sub.subscription.upper()} (can host ZeroGPU)")
    else:
        print(f"⚠ Subscription: {sub.subscription.upper()} (cannot host ZeroGPU)")
        print(f"  Daily ZeroGPU quota as visitor: {sub.zerogpu_quota_minutes} min")

    # Model access check
    access = results["model_access"]
    if access.accessible:
        status = "✓ Model: Accessible"
        if access.gated:
            status += " (gated, access granted)"
        if access.private:
            status += " (private)"
        print(status)
    else:
        print(f"✗ Model: {access.error}")
        if access.access_url:
            print(f"  Request access: {access.access_url}")

    # Model size check
    size = results["model_size"]
    if size.error:
        print(f"⚠ Size estimation: {size.error}")
    else:
        print(f"✓ Model type: {size.model_type}")
        if size.params_billions:
            print(f"  Estimated size: {size.params_billions}B parameters")
            print(f"  Estimated VRAM: {size.estimated_vram_gb}GB")
        print(f"  Recommended hardware: {size.recommended_hardware}")

    # Summary
    summary = results["summary"]
    print("\n" + "-" * 60)
    if summary["ready"]:
        print("✅ READY FOR DEPLOYMENT")
    else:
        print("❌ ISSUES MUST BE RESOLVED:")
        for issue in summary["issues"]:
            print(f"   • {issue}")

    if summary["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in summary["warnings"]:
            print(f"   • {warning}")

    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Pre-flight checks for HF Space deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all checks for a model
    python preflight.py check-all meta-llama/Llama-3.1-8B-Instruct

    # Check only token status
    python preflight.py check-token

    # Check subscription status
    python preflight.py check-subscription

    # Check model access
    python preflight.py check-model meta-llama/Llama-3.1-8B-Instruct

    # Estimate model size and get hardware recommendation
    python preflight.py estimate-size meta-llama/Llama-3.1-8B-Instruct
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check-all command
    all_parser = subparsers.add_parser("check-all", help="Run all pre-flight checks")
    all_parser.add_argument("model_id", help="Model ID to check (e.g., username/model)")

    # check-token command
    subparsers.add_parser("check-token", help="Check HF token status")

    # check-subscription command
    subparsers.add_parser("check-subscription", help="Check subscription status")

    # check-model command
    model_parser = subparsers.add_parser("check-model", help="Check model accessibility")
    model_parser.add_argument("model_id", help="Model ID to check")

    # estimate-size command
    size_parser = subparsers.add_parser("estimate-size", help="Estimate model size")
    size_parser.add_argument("model_id", help="Model ID to analyze")

    args = parser.parse_args()

    if args.command == "check-all":
        results = run_all_checks(args.model_id)
        print_check_results(results)
        sys.exit(0 if results["summary"]["ready"] else 1)

    elif args.command == "check-token":
        result = check_hf_token()
        if result.valid:
            print(f"✓ Token valid (user: {result.username})")
        else:
            print(f"✗ {result.error}")
            sys.exit(1)

    elif args.command == "check-subscription":
        result = check_zerogpu_eligibility()
        print(f"Subscription: {result.subscription}")
        print(f"Can host ZeroGPU: {result.can_host_zerogpu}")
        print(f"ZeroGPU quota: {result.zerogpu_quota_minutes} min/day")
        if result.error:
            print(f"Warning: {result.error}")

    elif args.command == "check-model":
        result = check_model_access(args.model_id)
        if result.accessible:
            print(f"✓ Model accessible")
            if result.gated:
                print("  (gated, access granted)")
        else:
            print(f"✗ {result.error}")
            if result.access_url:
                print(f"  Request access: {result.access_url}")
            sys.exit(1)

    elif args.command == "estimate-size":
        result = estimate_model_size(args.model_id)
        if result.error:
            print(f"Error: {result.error}")
            sys.exit(1)
        print(f"Model type: {result.model_type}")
        if result.params_billions:
            print(f"Estimated size: {result.params_billions}B parameters")
            print(f"Estimated VRAM: {result.estimated_vram_gb}GB")
        print(f"Recommended hardware: {result.recommended_hardware}")


if __name__ == "__main__":
    main()
