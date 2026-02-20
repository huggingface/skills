#!/usr/bin/env python3
"""
Manage Hugging Face Space settings: hardware, secrets, pause/restart.

Usage:
    python manage_space.py status username/my-space
    python manage_space.py hardware username/my-space --tier t4-small
    python manage_space.py secret username/my-space --key API_KEY --value xxx
    python manage_space.py pause username/my-space
    python manage_space.py restart username/my-space
"""

import argparse
import os
from huggingface_hub import (
    HfApi,
    request_space_hardware,
    add_space_secret,
    delete_space_secret,
    pause_space,
    restart_space,
    space_info,
)


def get_space_status(repo_id: str) -> dict:
    """Get current status of a Space."""
    api = HfApi()
    info = api.space_info(repo_id)

    status = {
        "id": info.id,
        "author": info.author,
        "sdk": info.sdk,
        "runtime": {
            "stage": info.runtime.stage if info.runtime else "unknown",
            "hardware": info.runtime.hardware if info.runtime else "unknown",
            "storage": info.runtime.storage if info.runtime else None,
        },
        "private": info.private,
        "likes": info.likes,
        "created_at": str(info.created_at) if info.created_at else None,
        "last_modified": str(info.last_modified) if info.last_modified else None,
    }

    return status


def print_status(repo_id: str):
    """Print formatted Space status."""
    print(f"\n📊 Space Status: {repo_id}")
    print("=" * 50)

    try:
        status = get_space_status(repo_id)

        print(f"  ID:        {status['id']}")
        print(f"  Author:    {status['author']}")
        print(f"  SDK:       {status['sdk']}")
        print(f"  Stage:     {status['runtime']['stage']}")
        print(f"  Hardware:  {status['runtime']['hardware']}")
        print(f"  Storage:   {status['runtime']['storage'] or 'None'}")
        print(f"  Private:   {status['private']}")
        print(f"  Likes:     {status['likes']}")
        print(f"  Created:   {status['created_at']}")
        print(f"  Modified:  {status['last_modified']}")
        print()
        print(f"  URL: https://huggingface.co/spaces/{repo_id}")

    except Exception as e:
        print(f"  Error: {e}")


def set_hardware(repo_id: str, hardware: str):
    """Change Space hardware tier."""
    print(f"\n⚙️  Setting hardware for {repo_id}")
    print(f"   New tier: {hardware}")

    request_space_hardware(repo_id=repo_id, hardware=hardware)
    print("   ✓ Hardware updated successfully")
    print("   Note: Space will restart with new hardware")


def add_secret(repo_id: str, key: str, value: str):
    """Add or update a Space secret."""
    print(f"\n🔐 Adding secret to {repo_id}")
    print(f"   Key: {key}")

    add_space_secret(repo_id=repo_id, key=key, value=value)
    print("   ✓ Secret added successfully")
    print(f"   Access in code: os.environ.get('{key}')")


def remove_secret(repo_id: str, key: str):
    """Remove a Space secret."""
    print(f"\n🔐 Removing secret from {repo_id}")
    print(f"   Key: {key}")

    delete_space_secret(repo_id=repo_id, key=key)
    print("   ✓ Secret removed successfully")


def pause(repo_id: str):
    """Pause a Space to stop billing."""
    print(f"\n⏸️  Pausing Space: {repo_id}")

    pause_space(repo_id=repo_id)
    print("   ✓ Space paused successfully")
    print("   Note: No charges while paused")


def restart(repo_id: str):
    """Restart a paused Space."""
    print(f"\n▶️  Restarting Space: {repo_id}")

    restart_space(repo_id=repo_id)
    print("   ✓ Space restart initiated")
    print("   Note: May take a few minutes to become available")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Hugging Face Space settings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status command
    status_parser = subparsers.add_parser("status", help="Get Space status")
    status_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    # Hardware command
    hw_parser = subparsers.add_parser("hardware", help="Change hardware tier")
    hw_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    hw_parser.add_argument(
        "--tier",
        required=True,
        choices=[
            "cpu-basic",
            "cpu-upgrade",
            "zero-a10g",
            "t4-small",
            "t4-medium",
            "l4",
            "l40s",
            "a10g-small",
            "a10g-large",
            "a100-large",
        ],
        help="Hardware tier",
    )

    # Secret commands
    secret_parser = subparsers.add_parser("secret", help="Add/update a secret")
    secret_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    secret_parser.add_argument("--key", required=True, help="Secret key name")
    secret_parser.add_argument("--value", required=True, help="Secret value")

    rm_secret_parser = subparsers.add_parser("rm-secret", help="Remove a secret")
    rm_secret_parser.add_argument("repo_id", help="Space ID (username/space-name)")
    rm_secret_parser.add_argument("--key", required=True, help="Secret key name")

    # Pause/Restart commands
    pause_parser = subparsers.add_parser("pause", help="Pause Space (stop billing)")
    pause_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    restart_parser = subparsers.add_parser("restart", help="Restart paused Space")
    restart_parser.add_argument("repo_id", help="Space ID (username/space-name)")

    args = parser.parse_args()

    # Execute command
    if args.command == "status":
        print_status(args.repo_id)
    elif args.command == "hardware":
        set_hardware(args.repo_id, args.tier)
    elif args.command == "secret":
        add_secret(args.repo_id, args.key, args.value)
    elif args.command == "rm-secret":
        remove_secret(args.repo_id, args.key)
    elif args.command == "pause":
        pause(args.repo_id)
    elif args.command == "restart":
        restart(args.repo_id)


if __name__ == "__main__":
    main()
