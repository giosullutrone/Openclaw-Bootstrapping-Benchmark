"""
Post-bootstrap verification.

After the bootstrap conversation finishes, this module inspects the
workspace files to determine whether the model successfully completed
the identity ritual.

Checks performed
----------------
1. BOOTSTRAP.md – must be **deleted** (the ritual says "delete when done").
2. IDENTITY.md  – must contain the expected agent identity values
   (name, creature, vibe, emoji) from ``bootstrap_fields``.
3. USER.md      – must contain the expected user values
   (name, timezone) from ``bootstrap_fields``.
4. SOUL.md      – must differ from the template (the agent should have
   personalised it).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import BootstrapFields

logger = logging.getLogger(__name__)

# ── Placeholder values from the OpenClaw templates ───────────
IDENTITY_PLACEHOLDERS = {
    "pick something you like",
    "ai? robot? familiar? ghost in the machine? something weirder?",
    "how do you come across? sharp? warm? chaotic? calm?",
    "your signature — pick one that feels right",
    "your signature - pick one that feels right",
    "workspace-relative path, http(s) url, or data uri",
}

USER_PLACEHOLDERS = {
    "",
    "(optional)",
}


@dataclass
class FileCheck:
    """Result of checking a single workspace file."""

    filename: str
    exists: bool = False
    passed: bool = False
    details: str = ""
    content: str = ""


@dataclass
class VerificationResult:
    """Aggregate result of all post-bootstrap checks."""

    model_name: str
    checks: list[FileCheck] = field(default_factory=list)
    all_passed: bool = False
    score: float = 0.0  # 0.0 – 1.0

    @property
    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c.passed)
        total = len(self.checks)
        return f"{passed}/{total} checks passed (score: {self.score:.0%})"


def _strip_md_markers(value: str) -> str:
    """Strip leading/trailing markdown bold/italic markers and whitespace."""
    return re.sub(r"^[*_\s]+|[*_\s]+$", "", value)


def _field_present(content: str, field: str) -> tuple[bool, str]:
    """Check whether *field* appears in *content* with a real value.

    Returns ``(found, extracted_value)``.  Uses two strategies:

    1. Structured: ``- **Field:** value`` or ``- Field: value``
    2. Loose: the word *field* appears anywhere near a non-placeholder
       value (handles prose, inline mentions, etc.)
    """
    lower = content.lower()

    # Strategy 1 — structured bullet / key-value line
    for line in content.splitlines():
        stripped = line.strip()
        m = re.match(
            r"^[-*]?\s*\*{0,2}"
            + re.escape(field)
            + r"\*{0,2}\s*[:=]\s*(.+)$",
            stripped,
            re.IGNORECASE,
        )
        if m:
            val = _strip_md_markers(m.group(1)).strip().rstrip(".")
            if val and not _is_placeholder(val):
                return True, val

    # Strategy 2 — the keyword followed by a colon/is + value anywhere
    m = re.search(
        r"\b" + re.escape(field) + r"\b\s*(?:is|:)\s*(.+?)(?:\.\s|\.|;|\n|$)",
        content,
        re.IGNORECASE,
    )
    if m:
        val = _strip_md_markers(m.group(1)).strip().rstrip(".")
        if val and not _is_placeholder(val):
            return True, val

    # Strategy 3 — for "name" specifically, handle "My name is X",
    # "I'm X", "called X"
    if field == "name":
        for pat in [
            r"\bname\b\s+is\s+(\w[\w\s-]*?)(?:\.|,|;|\n|$)",
            r"\bcall(?:ed)?\s+(\w[\w\s-]*?)(?:\.|,|;|\n|$)",
            r"\bi'?m\s+(\w[\w-]*?)(?:\.|,|;|\s|$)",
        ]:
            m = re.search(pat, lower)
            if m and m.group(1).strip():
                return True, m.group(1).strip().title()

    # Strategy 4 — for "timezone", also try "time zone"
    if field == "timezone":
        m = re.search(r"\btime\s*zone\b\s*(?:is|:)\s*([\w/+-]+)", content, re.IGNORECASE)
        if m and m.group(1).strip():
            return True, m.group(1).strip()

    return False, ""


def _is_placeholder(value: str) -> bool:
    """Check whether a value is still a template placeholder."""
    normalised = _strip_md_markers(value).lower().strip()
    return (
        normalised == ""
        or normalised in {p.lower() for p in IDENTITY_PLACEHOLDERS}
        or normalised in USER_PLACEHOLDERS
    )


# ── Individual file checks ──────────────────────────────────

def check_bootstrap_deleted(workspace: Path) -> FileCheck:
    """BOOTSTRAP.md must NOT exist (deleted after ritual)."""
    path = workspace / "BOOTSTRAP.md"
    exists = path.exists()
    content = ""
    if exists:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            pass
    return FileCheck(
        filename="BOOTSTRAP.md",
        exists=exists,
        passed=not exists,
        details="Deleted ✓" if not exists else "Still exists — bootstrap did not complete",
        content=content,
    )


def check_identity(workspace: Path, expected: dict[str, str] | None = None) -> FileCheck:
    """IDENTITY.md must have the expected agent identity values."""
    path = workspace / "IDENTITY.md"
    check = FileCheck(filename="IDENTITY.md", exists=path.exists())

    if not path.exists():
        check.details = "File missing"
        return check

    content = path.read_text(encoding="utf-8")
    check.content = content

    if not expected:
        # Fallback: just check the file isn't empty/template-only
        if len(content.strip()) > 100:
            check.passed = True
            check.details = f"Has content ({len(content)} chars)"
        else:
            check.details = "File appears empty or template-only"
        return check

    # Check that each expected value actually appears in the content
    missing = []
    found: dict[str, str] = {}
    content_lower = content.lower()
    for field_name, expected_val in expected.items():
        if expected_val.lower() in content_lower:
            found[field_name] = expected_val
        else:
            # Also try via _field_present (handles "name is X" etc.)
            present, val = _field_present(content, field_name)
            if present:
                found[field_name] = val
            else:
                missing.append(field_name)

    if missing:
        check.details = f"Missing fields: {', '.join(missing)}"
    else:
        check.passed = True
        check.details = f"All fields set: {', '.join(f'{k}={found[k]}' for k in expected)}"

    return check


def check_user(workspace: Path, expected: dict[str, str] | None = None) -> FileCheck:
    """USER.md must have the expected user values."""
    path = workspace / "USER.md"
    check = FileCheck(filename="USER.md", exists=path.exists())

    if not path.exists():
        check.details = "File missing"
        return check

    content = path.read_text(encoding="utf-8")
    check.content = content

    if not expected:
        if len(content.strip()) > 50:
            check.passed = True
            check.details = f"Has content ({len(content)} chars)"
        else:
            check.details = "File appears empty or template-only"
        return check

    missing = []
    found: dict[str, str] = {}
    content_lower = content.lower()
    for field_name, expected_val in expected.items():
        if expected_val.lower() in content_lower:
            found[field_name] = expected_val
        else:
            present, val = _field_present(content, field_name)
            if not present and field_name == "name":
                present, val = _field_present(content, "what to call them")
            if present:
                found[field_name] = val
            else:
                missing.append(field_name)

    if missing:
        check.details = f"Missing fields: {', '.join(missing)}"
    else:
        check.passed = True
        check.details = f"Key fields populated: {', '.join(f'{k}={found[k]}' for k in expected)}"

    return check


def check_soul(workspace: Path) -> FileCheck:
    """SOUL.md must have been modified from the default template."""
    path = workspace / "SOUL.md"
    check = FileCheck(filename="SOUL.md", exists=path.exists())

    if not path.exists():
        check.details = "File missing"
        return check

    content = path.read_text(encoding="utf-8")
    check.content = content

    # The template is quite short; if the file has substantial content
    # and doesn't exactly match certain template phrases, it was updated.
    template_markers = [
        "Fill this in during your first conversation",
        "You're not a chatbot. You're becoming someone.",
    ]
    has_template_only = all(marker in content for marker in template_markers)
    is_long_enough = len(content.strip()) > 200

    if has_template_only and not is_long_enough:
        check.details = "Still contains only template text"
    else:
        check.passed = True
        check.details = f"Modified ({len(content)} chars)"

    return check


# ── Aggregate verification ───────────────────────────────────

def verify_bootstrap(
    workspace: Path,
    model_name: str,
    bootstrap_fields: BootstrapFields | None = None,
) -> VerificationResult:
    """Run all post-bootstrap checks and return aggregated results."""
    identity_expected = bootstrap_fields.identity_expected if bootstrap_fields else None
    user_expected = bootstrap_fields.user_expected if bootstrap_fields else None

    checks = [
        check_bootstrap_deleted(workspace),
        check_identity(workspace, expected=identity_expected),
        check_user(workspace, expected=user_expected),
        check_soul(workspace),
    ]

    passed = sum(1 for c in checks if c.passed)
    total = len(checks)

    result = VerificationResult(
        model_name=model_name,
        checks=checks,
        all_passed=(passed == total),
        score=passed / total if total > 0 else 0.0,
    )

    for c in checks:
        status = "✅" if c.passed else "❌"
        logger.info("  %s %s: %s", status, c.filename, c.details)

    return result
