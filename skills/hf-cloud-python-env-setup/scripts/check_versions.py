#!/usr/bin/env python
"""Report installed versions of key dependencies.

Uses importlib.metadata.version() (works for every installed package, unlike
the inconsistently-defined `module.__version__`).

Usage:
    python check_versions.py
    python check_versions.py boto3 botocore transformers
"""

import sys
from importlib.metadata import PackageNotFoundError, version

DEFAULT_PACKAGES = ["boto3", "botocore", "awscli"]


def main() -> int:
    packages = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_PACKAGES
    for pkg in packages:
        try:
            print(f"{pkg}=={version(pkg)}")
        except PackageNotFoundError:
            print(f"{pkg}: NOT INSTALLED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
