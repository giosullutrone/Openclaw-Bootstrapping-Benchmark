"""
Pre-flight checks.

Validates that all external prerequisites are in place before spending
time on actual benchmark runs.  Each check produces a clear pass / fail
with actionable fix instructions.

Checks
------
1. Node.js ≥ 22
2. npm available
3. Gateway port available
4. Each model server is reachable (HTTP probe to ``base_url``)
5. Each model is loaded / pullable (``/v1/models`` probe)
"""

from __future__ import annotations

import logging
import re
import socket
import sys
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import BenchmarkConfig, ModelConfig

logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    fix_hint: str = ""


@dataclass
class PreflightReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


# ── Individual checks ────────────────────────────────────────

def _run_command(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Returns ``(-1, "", error_message)`` when the binary is missing or
    the command times out.
    """
    import subprocess

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"


def check_node() -> CheckResult:
    """Node.js ≥ 22 must be installed."""
    rc, out, err = _run_command(["node", "--version"])
    if rc != 0:
        return CheckResult(
            name="Node.js",
            passed=False,
            message=err or "node not found",
            fix_hint="Install Node.js ≥ 22: https://nodejs.org/ or `brew install node@22`",
        )

    # Parse version: v22.1.0 → (22, 1, 0)
    m = re.match(r"v?(\d+)", out)
    if not m:
        return CheckResult(
            name="Node.js",
            passed=False,
            message=f"Could not parse version from: {out}",
            fix_hint="Install Node.js ≥ 22",
        )

    major = int(m.group(1))
    if major < 22:
        return CheckResult(
            name="Node.js",
            passed=False,
            message=f"Found v{out.lstrip('v')} — need ≥ 22",
            fix_hint="Upgrade Node.js: `nvm install 22` or `brew install node@22`",
        )

    return CheckResult(
        name="Node.js",
        passed=True,
        message=f"v{out.lstrip('v')}",
    )


def check_npm() -> CheckResult:
    """npm must be available."""
    rc, out, err = _run_command(["npm", "--version"])
    if rc != 0:
        return CheckResult(
            name="npm",
            passed=False,
            message=err or "npm not found",
            fix_hint="npm ships with Node.js — reinstall Node or run `npm install -g npm`",
        )
    return CheckResult(name="npm", passed=True, message=f"v{out}")


def check_port(port: int) -> CheckResult:
    """The gateway port must be free."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            # Port is in use
            return CheckResult(
                name=f"Port {port}",
                passed=False,
                message=f"Port {port} is already in use",
                fix_hint=(
                    f"Free the port: `lsof -ti:{port} | xargs kill` or "
                    f"change `gateway.port` in config.yaml"
                ),
            )
        return CheckResult(
            name=f"Port {port}",
            passed=True,
            message="Available",
        )
    except OSError as exc:
        return CheckResult(
            name=f"Port {port}",
            passed=True,  # assume available if we can't connect
            message=f"Assumed available ({exc})",
        )
    finally:
        sock.close()


def check_model_server(model: ModelConfig) -> CheckResult:
    """The model's base_url must respond to HTTP requests."""
    # Probe the /models endpoint (OpenAI-compatible)
    url = model.base_url.rstrip("/")
    # Try /models first (standard OpenAI-compat), fall back to base URL
    probe_urls = [f"{url}/models", url]

    for probe_url in probe_urls:
        try:
            req = Request(probe_url, method="GET")
            if model.api_key:
                req.add_header("Authorization", f"Bearer {model.api_key}")
            with urlopen(req, timeout=5) as resp:
                if resp.status < 400:
                    return CheckResult(
                        name=f"Server [{model.name}]",
                        passed=True,
                        message=f"Reachable at {probe_url}",
                    )
        except (URLError, OSError, TimeoutError):
            continue

    return CheckResult(
        name=f"Server [{model.name}]",
        passed=False,
        message=f"Cannot reach {url}",
        fix_hint=(
            f"Start your model server (e.g. `ollama serve`) and ensure "
            f"it listens on {url}"
        ),
    )


def check_model_available(model: ModelConfig) -> CheckResult:
    """The specific model must be loaded / available on the server."""
    import json as _json

    url = model.base_url.rstrip("/") + "/models"
    try:
        req = Request(url, method="GET")
        if model.api_key:
            req.add_header("Authorization", f"Bearer {model.api_key}")
        with urlopen(req, timeout=10) as resp:
            body = _json.loads(resp.read().decode())
    except (URLError, OSError, TimeoutError, ValueError):
        # Server unreachable — already covered by check_model_server
        return CheckResult(
            name=f"Model [{model.name}]",
            passed=False,
            message=f"Could not list models from {url}",
            fix_hint=f"Ensure server is running at {model.base_url}",
        )

    # OpenAI-compatible: { "data": [ { "id": "model-name" }, ... ] }
    model_ids: set[str] = set()
    if isinstance(body, dict) and "data" in body:
        for entry in body["data"]:
            if isinstance(entry, dict) and "id" in entry:
                model_ids.add(entry["id"])
    # Ollama also supports { "models": [ { "name": "..." } ] }
    elif isinstance(body, dict) and "models" in body:
        for entry in body["models"]:
            if isinstance(entry, dict):
                name = entry.get("model") or entry.get("name", "")
                model_ids.add(name)
                # Ollama names often have :tag — also add without tag
                if ":" in name:
                    model_ids.add(name.split(":")[0])

    wanted = model.model_id
    # Normalise: try exact match, then without tag
    found = wanted in model_ids
    if not found and ":" in wanted:
        found = wanted.split(":")[0] in model_ids
    # Also try with :latest for bare names
    if not found:
        found = f"{wanted}:latest" in model_ids

    if found:
        return CheckResult(
            name=f"Model [{model.name}]",
            passed=True,
            message=f"'{wanted}' available",
        )

    available = ", ".join(sorted(model_ids)[:10]) or "(none)"
    return CheckResult(
        name=f"Model [{model.name}]",
        passed=False,
        message=f"'{wanted}' not found on server",
        fix_hint=(
            f"Pull the model first: e.g. `ollama pull {wanted}`\n"
            f"         Available models: {available}"
        ),
    )


# ── Aggregate runner ─────────────────────────────────────────

def run_preflight(cfg: BenchmarkConfig, *, skip_install: bool = False) -> PreflightReport:
    """Run all pre-flight checks and return the report."""
    report = PreflightReport()

    # System-level checks
    if not skip_install:
        report.checks.append(check_node())
        report.checks.append(check_npm())

    report.checks.append(check_port(cfg.gateway.port))

    # Per-model checks — deduplicate servers with the same base_url
    seen_urls: set[str] = set()
    for model in cfg.models:
        if model.base_url not in seen_urls:
            report.checks.append(check_model_server(model))
            seen_urls.add(model.base_url)
        report.checks.append(check_model_available(model))

    return report


def print_preflight(report: PreflightReport, console: Console | None = None) -> None:
    """Print the pre-flight report as a rich table."""
    if console is None:
        console = Console()

    table = Table(
        title="🔍 Pre-flight Checks",
        show_lines=True,
    )
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center", width=6)
    table.add_column("Details")
    table.add_column("Fix", style="dim")

    for c in report.checks:
        status = "[green]✅[/green]" if c.passed else "[red]❌[/red]"
        table.add_row(c.name, status, c.message, c.fix_hint or "—")

    console.print()
    console.print(table)
    console.print()

    if report.all_passed:
        console.print(
            Panel(
                "[green bold]All pre-flight checks passed — ready to benchmark![/green bold]",
                border_style="green",
            )
        )
    else:
        n_fail = len(report.failed)
        console.print(
            Panel(
                f"[red bold]{n_fail} check(s) failed — fix the issues above before running.[/red bold]",
                border_style="red",
            )
        )
