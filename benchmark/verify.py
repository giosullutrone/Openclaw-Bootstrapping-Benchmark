"""
Post-bootstrap verification.

After the bootstrap conversation finishes, this module inspects the
workspace files to determine whether the model successfully completed
the identity ritual.

Checks performed
----------------
1. BOOTSTRAP.md – must be **deleted** (the ritual says "delete when done").
2. IDENTITY.md  – must contain non-placeholder values for Name, Creature,
   Vibe, and Emoji.
3. USER.md      – must contain non-placeholder values for Name and Timezone.
4. SOUL.md      – must differ from the template (the agent should have
   personalised it).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

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

# Fields we require in IDENTITY.md
IDENTITY_REQUIRED_FIELDS = {"name", "creature", "vibe", "emoji"}

# Fields we require in USER.md
USER_REQUIRED_FIELDS = {"name", "timezone"}


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


def _parse_md_fields(content: str) -> dict[str, str]:
    """Extract ``- **Key:** Value`` or ``- Key: Value`` lines from markdown.

    Also looks for continuation-line placeholder text such as::

        - **Name:**
          _(pick something you like)_
    """
    fields: dict[str, str] = {}
    lines = content.splitlines()
    for idx, raw in enumerate(lines):
        line = raw.strip()
        # Match: - **Name:** Coral  OR  - Name: Coral  OR  * **Name:** Coral
        m = re.match(r"^[-*]\s*\*{0,2}(\w[\w\s]*?)\*{0,2}\s*:\s*(.*)$", line)
        if m:
            key = m.group(1).strip().lower()
            val = _strip_md_markers(m.group(2))
            # Also strip parenthetical wrappers like _(text)_
            val = val.strip("(").strip(")").strip()

            # If the value is empty, check the next line for a continuation
            # (OpenClaw templates put the placeholder on a separate line)
            if not val and idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                if next_line and not re.match(r"^[-*]\s", next_line):
                    val = _strip_md_markers(next_line)
                    val = val.strip("(").strip(")").strip()

            fields[key] = val
    return fields


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


def check_identity(workspace: Path) -> FileCheck:
    """IDENTITY.md must have real values for required fields."""
    path = workspace / "IDENTITY.md"
    check = FileCheck(filename="IDENTITY.md", exists=path.exists())

    if not path.exists():
        check.details = "File missing"
        return check

    content = path.read_text(encoding="utf-8")
    check.content = content
    fields = _parse_md_fields(content)

    missing = []
    placeholder = []
    for req in IDENTITY_REQUIRED_FIELDS:
        val = fields.get(req, "")
        if not val:
            missing.append(req)
        elif _is_placeholder(val):
            placeholder.append(req)

    if missing:
        check.details = f"Missing fields: {', '.join(missing)}"
    elif placeholder:
        check.details = f"Placeholder values: {', '.join(placeholder)}"
    else:
        check.passed = True
        check.details = f"All fields set: {', '.join(f'{k}={fields[k]}' for k in IDENTITY_REQUIRED_FIELDS)}"

    return check


def check_user(workspace: Path) -> FileCheck:
    """USER.md must have real values for required fields."""
    path = workspace / "USER.md"
    check = FileCheck(filename="USER.md", exists=path.exists())

    if not path.exists():
        check.details = "File missing"
        return check

    content = path.read_text(encoding="utf-8")
    check.content = content
    fields = _parse_md_fields(content)

    missing = []
    placeholder = []
    for req in USER_REQUIRED_FIELDS:
        val = fields.get(req, "")
        # "what to call them" is sometimes used instead of "name"
        if req == "name" and not val:
            val = fields.get("what to call them", "")
        if not val:
            missing.append(req)
        elif _is_placeholder(val):
            placeholder.append(req)

    if missing:
        check.details = f"Missing fields: {', '.join(missing)}"
    elif placeholder:
        check.details = f"Placeholder values: {', '.join(placeholder)}"
    else:
        check.passed = True
        parts = []
        for k in USER_REQUIRED_FIELDS:
            v = fields.get(k, "") or fields.get("what to call them", "")
            parts.append(f"{k}={v}")
        check.details = f"Key fields populated: {', '.join(parts)}"

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

def verify_bootstrap(workspace: Path, model_name: str) -> VerificationResult:
    """Run all post-bootstrap checks and return aggregated results."""
    checks = [
        check_bootstrap_deleted(workspace),
        check_identity(workspace),
        check_user(workspace),
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
