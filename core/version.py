from __future__ import annotations

import subprocess
from pathlib import Path

PACKAGE_VERSION = "1.1.0"
ROOT = Path(__file__).resolve().parent.parent


def code_version() -> str:
    # results/ and documentation do not affect behaviour, so they do not mark the tree dirty
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", ".", ":!results", ":!*.md"], cwd=ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        if sha:
            return f"{PACKAGE_VERSION}+g{sha}{'.dirty' if dirty else ''}"
    except Exception:
        pass
    return f"{PACKAGE_VERSION}+nogit"
