"""Core detection engine for downstream breakage scanning.

Provides the primary data structures and risk-detection logic used by the
CLI and the GitHub Action.  Everything here is stdlib-only.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISKY_PATH_MARKERS: tuple[str, ...] = (
    "src/",
    "lib/",
    "app/",
    "api/",
    "public/",
    "include/",
    "internal/",
    "pkg/",
    "schemas/",
    "proto/",
    "openapi",
)

RISKY_FILENAMES: set[str] = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "gradle.properties",
}

SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".java", ".kt", ".cs",
)

SEVERITY_ORDER: dict[str, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """A single risk finding produced by the scanner."""

    severity: str
    path: str
    message: str
    migration_note: str


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_changed_files(repo_path: Path, base_ref: str) -> list[str]:
    """Return the list of file paths changed between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def git_diff(repo_path: Path, base_ref: str) -> str:
    """Return the unified diff between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def git_deleted_files(repo_path: Path, base_ref: str) -> list[str]:
    """Return file paths that were deleted between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", "--diff-filter=D", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Risk detection
# ---------------------------------------------------------------------------

def detect_risk(changed_files: Iterable[str]) -> list[Finding]:
    """Analyse *changed_files* and return findings based on path heuristics.

    This function only inspects file names/paths.  For diff-level analysis
    use :func:`downstream_breakage_radar.diff_analyzer.analyze_diff`.
    """

    findings: list[Finding] = []
    for path in changed_files:
        lowered = path.lower()
        filename = Path(path).name

        # Medium: risky path or config file
        if filename in RISKY_FILENAMES or any(marker in lowered for marker in RISKY_PATH_MARKERS):
            findings.append(
                Finding(
                    severity="medium",
                    path=path,
                    message="Change touches a likely public surface or release-critical file.",
                    migration_note="Review for API compatibility, config drift, and release notes before merging.",
                )
            )

        # Low: any source code change
        if lowered.endswith(SOURCE_EXTENSIONS):
            findings.append(
                Finding(
                    severity="low",
                    path=path,
                    message="Source code change may affect downstream consumers.",
                    migration_note="Check for renamed symbols, changed defaults, and behavior shifts.",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------

def summarize(findings: list[Finding], changed_files: list[str]) -> dict[str, object]:
    """Build a summary dict from a list of findings and changed files."""

    highest = "none"
    for f in findings:
        sev = f.severity
        if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(highest, 0):
            highest = sev

    return {
        "changed_files": changed_files,
        "change_count": len(changed_files),
        "risk_level": highest,
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }
