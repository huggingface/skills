#!/usr/bin/env python3
"""
Auto-remediate common Hugging Face Space deployment issues.

Provides automated fixes for common problems:
- Missing packages in requirements.txt
- Hardware mismatches
- Missing secrets
- Version conflicts

Usage:
    python remediate.py fix-requirements username/my-space --add torch transformers
    python remediate.py fix-hardware username/my-space --tier zero-a10g
    python remediate.py add-secret username/my-space --key HF_TOKEN --value xxx
    python remediate.py auto-fix username/my-space
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

from huggingface_hub import (
    HfApi,
    hf_hub_download,
    upload_file,
    add_space_secret,
    request_space_hardware,
    restart_space,
)

from monitor_space import get_build_logs, get_runtime_logs, detect_errors, DetectedError


# Known package fixes for common import errors
PACKAGE_FIXES = {
    "torch": "torch",
    "transformers": "transformers>=4.40.0",
    "accelerate": "accelerate",
    "spaces": "spaces",
    "peft": "peft",
    "gradio": "gradio>=5.0.0",
    "huggingface_hub": "huggingface_hub>=0.26.0",
    "sentence_transformers": "sentence-transformers>=2.2.0",
    "PIL": "Pillow>=10.0.0",
    "cv2": "opencv-python>=4.8.0",
    "numpy": "numpy>=1.24.0",
    "scipy": "scipy>=1.10.0",
    "sklearn": "scikit-learn>=1.3.0",
    "pandas": "pandas>=2.0.0",
    "matplotlib": "matplotlib>=3.7.0",
    "torchaudio": "torchaudio",
    "torchvision": "torchvision",
    "diffusers": "diffusers>=0.25.0",
    "safetensors": "safetensors>=0.4.0",
    "bitsandbytes": "bitsandbytes",
    "einops": "einops",
    "timm": "timm",
    "soundfile": "soundfile",
    "librosa": "librosa",
    "tiktoken": "tiktoken",
    "sentencepiece": "sentencepiece",
}

# Version fixes for known compatibility issues
VERSION_FIXES = {
    "gradio_hffolder": {
        "gradio": "gradio>=5.0.0",
        "huggingface_hub": "huggingface_hub>=0.26.0",
    },
}


def get_current_requirements(repo_id: str) -> list[str]:
    """Download and parse current requirements.txt from a Space."""
    try:
        req_path = hf_hub_download(
            repo_id=repo_id,
            filename="requirements.txt",
            repo_type="space",
        )
        with open(req_path) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception:
        return []


def add_packages_to_requirements(
    repo_id: str,
    packages: list[str],
    dry_run: bool = False,
) -> bool:
    """
    Add missing packages to requirements.txt and upload.

    Args:
        repo_id: Space repository ID
        packages: List of packages to add
        dry_run: If True, show what would be changed without making changes

    Returns:
        True if successful
    """
    current_reqs = get_current_requirements(repo_id)

    # Normalize package names for comparison
    def normalize(pkg: str) -> str:
        # Extract package name without version specifier
        match = re.match(r"([a-zA-Z0-9_-]+)", pkg)
        return match.group(1).lower().replace("-", "_") if match else pkg.lower()

    current_normalized = {normalize(r) for r in current_reqs}

    # Find packages to add
    packages_to_add = []
    for pkg in packages:
        # Map common import names to package names
        pkg_spec = PACKAGE_FIXES.get(pkg, pkg)
        pkg_name = normalize(pkg_spec)

        if pkg_name not in current_normalized:
            packages_to_add.append(pkg_spec)

    if not packages_to_add:
        print("All packages already present in requirements.txt")
        return True

    # Create new requirements
    new_reqs = current_reqs + packages_to_add
    new_content = "\n".join(new_reqs) + "\n"

    print(f"\nPackages to add: {', '.join(packages_to_add)}")
    print(f"\nNew requirements.txt:")
    print("-" * 40)
    print(new_content)
    print("-" * 40)

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        return True

    # Upload new requirements.txt
    try:
        upload_file(
            path_or_fileobj=new_content.encode(),
            path_in_repo="requirements.txt",
            repo_id=repo_id,
            repo_type="space",
            commit_message=f"Add packages: {', '.join(packages_to_add)}",
        )
        print(f"\n✓ Updated requirements.txt")
        print("  Space will automatically rebuild.")
        return True
    except Exception as e:
        print(f"\n✗ Failed to update requirements.txt: {e}")
        return False


def fix_version_conflicts(
    repo_id: str,
    error_type: str,
    dry_run: bool = False,
) -> bool:
    """
    Fix known version conflicts in requirements.txt.

    Args:
        repo_id: Space repository ID
        error_type: Type of version conflict (e.g., "gradio_hffolder")
        dry_run: If True, show what would be changed without making changes

    Returns:
        True if successful
    """
    if error_type not in VERSION_FIXES:
        print(f"Unknown version conflict type: {error_type}")
        return False

    fixes = VERSION_FIXES[error_type]
    current_reqs = get_current_requirements(repo_id)

    # Update package versions
    new_reqs = []
    for req in current_reqs:
        # Extract package name
        match = re.match(r"([a-zA-Z0-9_-]+)", req)
        if match:
            pkg_name = match.group(1).lower().replace("-", "_")
            # Check if this package needs a version fix
            for fix_pkg, fix_spec in fixes.items():
                if pkg_name == fix_pkg.lower().replace("-", "_"):
                    new_reqs.append(fix_spec)
                    break
            else:
                new_reqs.append(req)
        else:
            new_reqs.append(req)

    # Add any missing packages from fixes
    current_normalized = {re.match(r"([a-zA-Z0-9_-]+)", r).group(1).lower().replace("-", "_")
                          for r in new_reqs if re.match(r"([a-zA-Z0-9_-]+)", r)}

    for fix_pkg, fix_spec in fixes.items():
        if fix_pkg.lower().replace("-", "_") not in current_normalized:
            new_reqs.append(fix_spec)

    new_content = "\n".join(new_reqs) + "\n"

    print(f"\nApplying version fixes for: {error_type}")
    print(f"\nNew requirements.txt:")
    print("-" * 40)
    print(new_content)
    print("-" * 40)

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        return True

    try:
        upload_file(
            path_or_fileobj=new_content.encode(),
            path_in_repo="requirements.txt",
            repo_id=repo_id,
            repo_type="space",
            commit_message=f"Fix version conflict: {error_type}",
        )
        print(f"\n✓ Updated requirements.txt")
        return True
    except Exception as e:
        print(f"\n✗ Failed to update requirements.txt: {e}")
        return False


def set_hardware(repo_id: str, hardware: str, dry_run: bool = False) -> bool:
    """
    Change Space hardware tier.

    Args:
        repo_id: Space repository ID
        hardware: Hardware tier (e.g., "zero-a10g", "t4-small")
        dry_run: If True, show what would be changed without making changes

    Returns:
        True if successful
    """
    print(f"\nSetting hardware for {repo_id} to: {hardware}")

    if dry_run:
        print("[DRY RUN] No changes made.")
        return True

    try:
        request_space_hardware(repo_id=repo_id, hardware=hardware)
        print(f"✓ Hardware updated to {hardware}")
        print("  Space will restart with new hardware.")
        return True
    except Exception as e:
        print(f"✗ Failed to update hardware: {e}")
        return False


def add_secret(repo_id: str, key: str, value: str, dry_run: bool = False) -> bool:
    """
    Add or update a Space secret.

    Args:
        repo_id: Space repository ID
        key: Secret key name
        value: Secret value
        dry_run: If True, show what would be changed without making changes

    Returns:
        True if successful
    """
    print(f"\nAdding secret '{key}' to {repo_id}")

    if dry_run:
        print("[DRY RUN] No changes made.")
        return True

    try:
        add_space_secret(repo_id=repo_id, key=key, value=value)
        print(f"✓ Secret '{key}' added")
        print(f"  Access in code: os.environ.get('{key}')")
        return True
    except Exception as e:
        print(f"✗ Failed to add secret: {e}")
        return False


def auto_fix(repo_id: str, dry_run: bool = False) -> dict:
    """
    Automatically detect and fix common issues.

    Analyzes Space logs, detects errors, and applies automatic fixes
    for issues that can be resolved programmatically.

    Args:
        repo_id: Space repository ID
        dry_run: If True, show what would be fixed without making changes

    Returns:
        Dict with fix results
    """
    results = {
        "analyzed": True,
        "errors_found": 0,
        "fixes_applied": 0,
        "fixes_available": 0,
        "manual_fixes_needed": [],
    }

    print(f"\n{'=' * 60}")
    print(f"AUTO-FIX: {repo_id}")
    print("=" * 60)

    # Fetch and analyze logs
    print("\nFetching logs...")
    logs = get_build_logs(repo_id) + "\n" + get_runtime_logs(repo_id)
    errors = detect_errors(logs)

    results["errors_found"] = len(errors)

    if not errors:
        print("\n✅ No errors detected in logs.")
        return results

    print(f"\nFound {len(errors)} error(s)")

    # Group errors by type for deduplication
    errors_by_type: dict[str, DetectedError] = {}
    for error in errors:
        if error.error_type not in errors_by_type:
            errors_by_type[error.error_type] = error

    # Process each error type
    packages_to_add = []

    for error_type, error in errors_by_type.items():
        print(f"\n--- {error.description} ---")

        if error.auto_fixable:
            results["fixes_available"] += 1

            if error_type == "module_not_found":
                # Extract package name and add to list
                if error.match_groups:
                    pkg = error.match_groups[0]
                    packages_to_add.append(pkg)
                    print(f"  Will add package: {pkg}")

            elif error_type == "gradio_hffolder":
                # Fix version conflict
                print("  Will fix Gradio/huggingface_hub versions")
                if not dry_run:
                    if fix_version_conflicts(repo_id, "gradio_hffolder", dry_run):
                        results["fixes_applied"] += 1

            elif error_type == "gradio_examples_format":
                print("  ⚠️  Examples format needs manual fix in app.py")
                print(f"     Fix: {error.fix_suggestion}")
                results["manual_fixes_needed"].append(error.fix_suggestion)

            elif error_type == "port_in_use":
                print("  ⚠️  Port binding needs manual fix in app.py")
                print("     Remove explicit port in demo.launch()")
                results["manual_fixes_needed"].append(error.fix_suggestion)

        else:
            results["manual_fixes_needed"].append(error.fix_suggestion)
            print(f"  ⚠️  Manual fix required: {error.fix_suggestion}")

    # Apply package additions
    if packages_to_add:
        print(f"\n--- Adding missing packages ---")
        if add_packages_to_requirements(repo_id, packages_to_add, dry_run):
            results["fixes_applied"] += len(packages_to_add)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Errors found: {results['errors_found']}")
    print(f"Auto-fixes available: {results['fixes_available']}")
    print(f"Fixes applied: {results['fixes_applied']}")

    if results["manual_fixes_needed"]:
        print(f"\nManual fixes needed ({len(results['manual_fixes_needed'])}):")
        for i, fix in enumerate(results["manual_fixes_needed"], 1):
            print(f"  {i}. {fix}")

    if results["fixes_applied"] > 0 and not dry_run:
        print("\n✓ Space will automatically rebuild with fixes.")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Auto-remediate HF Space issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Add missing packages
    python remediate.py fix-requirements username/my-space --add torch transformers

    # Fix hardware mismatch
    python remediate.py fix-hardware username/my-space --tier zero-a10g

    # Add a secret
    python remediate.py add-secret username/my-space --key HF_TOKEN --value hf_xxx

    # Auto-detect and fix issues
    python remediate.py auto-fix username/my-space

    # Dry run (show what would be fixed)
    python remediate.py auto-fix username/my-space --dry-run
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # fix-requirements command
    req_parser = subparsers.add_parser("fix-requirements", help="Add packages to requirements.txt")
    req_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    req_parser.add_argument("--add", nargs="+", required=True, help="Packages to add")
    req_parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # fix-hardware command
    hw_parser = subparsers.add_parser("fix-hardware", help="Change hardware tier")
    hw_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    hw_parser.add_argument("--tier", required=True, help="Hardware tier")
    hw_parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # add-secret command
    secret_parser = subparsers.add_parser("add-secret", help="Add a Space secret")
    secret_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    secret_parser.add_argument("--key", required=True, help="Secret key name")
    secret_parser.add_argument("--value", required=True, help="Secret value")
    secret_parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # auto-fix command
    auto_parser = subparsers.add_parser("auto-fix", help="Auto-detect and fix issues")
    auto_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    auto_parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    # restart command
    restart_parser = subparsers.add_parser("restart", help="Restart a Space")
    restart_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    args = parser.parse_args()

    if args.command == "fix-requirements":
        success = add_packages_to_requirements(args.repo_id, args.add, args.dry_run)
        sys.exit(0 if success else 1)

    elif args.command == "fix-hardware":
        success = set_hardware(args.repo_id, args.tier, args.dry_run)
        sys.exit(0 if success else 1)

    elif args.command == "add-secret":
        success = add_secret(args.repo_id, args.key, args.value, args.dry_run)
        sys.exit(0 if success else 1)

    elif args.command == "auto-fix":
        results = auto_fix(args.repo_id, args.dry_run)
        # Exit with error if manual fixes are needed
        sys.exit(0 if not results["manual_fixes_needed"] else 1)

    elif args.command == "restart":
        try:
            restart_space(args.repo_id)
            print(f"✓ Space {args.repo_id} restart initiated")
        except Exception as e:
            print(f"✗ Failed to restart: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
