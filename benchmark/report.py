"""
Results reporting.

Produces:
* A rich terminal table summarising all model runs.
* A JSON report written to ``results/`` for programmatic consumption.
* A markdown results table that is auto-injected into ``README.md``
  between ``<!-- BENCHMARK RESULTS -->`` markers.

Reports are sanitised: API keys and other secret-looking values are
redacted before being written to disk.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .bootstrap import BootstrapResult
from .verify import FileCheck, VerificationResult

logger = logging.getLogger(__name__)

# Patterns that look like secret values (Bearer tokens, long hex, etc.)
_SECRET_PATTERNS = re.compile(
    r"(Bearer\s+)\S+|"              # Bearer <token>
    r"(api[_-]?key[\"':\s=]+)\S+|"  # api_key = <value>
    r"(apiKey[\"':\s=]+)\S+",       # apiKey: <value>
    flags=re.IGNORECASE,
)

# Markers in README.md for auto-injected results
_RESULTS_START = "<!-- BENCHMARK RESULTS -->"
_RESULTS_END = "<!-- /BENCHMARK RESULTS -->"


# ── Aggregated result across N runs ──────────────────────────

@dataclass
class AggregatedResult:
    """Averaged results for a single model across multiple runs."""

    model_name: str
    runs: list[tuple[BootstrapResult, VerificationResult]]
    prompt_variant: str = "default"
    prompt_variant_prompts: list[str] = field(default_factory=list)
    # Raw JSON run data carried over from a previous report (used by
    # --skip-completed so that the final report preserves full detail).
    _raw_runs_json: list[dict] = field(default_factory=list, repr=False)
    num_runs: int = 0
    avg_score: float = 0.0
    avg_duration_s: float = 0.0
    bootstrap_rate: float = 0.0  # fraction of runs where bootstrap completed
    perfect_rate: float = 0.0   # fraction of runs where all checks passed
    # Per-check pass rates
    bootstrap_md_rate: float = 0.0
    identity_rate: float = 0.0
    user_rate: float = 0.0
    soul_rate: float = 0.0


def aggregate_runs(
    model_name: str,
    runs: list[tuple[BootstrapResult, VerificationResult]],
    prompt_variant: str = "default",
    prompt_variant_prompts: list[str] | None = None,
) -> AggregatedResult:
    """Aggregate multiple independent runs into averaged statistics."""
    n = len(runs)
    if n == 0:
        return AggregatedResult(
            model_name=model_name, runs=[], prompt_variant=prompt_variant,
            prompt_variant_prompts=prompt_variant_prompts or [],
        )

    scores = [vr.score for _, vr in runs]
    durations = [br.total_duration_s for br, _ in runs]

    def _check_rate(filename: str) -> float:
        passed = 0
        for _, vr in runs:
            for c in vr.checks:
                if c.filename == filename and c.passed:
                    passed += 1
        return passed / n

    return AggregatedResult(
        model_name=model_name,
        runs=runs,
        prompt_variant=prompt_variant,
        prompt_variant_prompts=prompt_variant_prompts or [],
        num_runs=n,
        avg_score=sum(scores) / n,
        avg_duration_s=sum(durations) / n,
        bootstrap_rate=sum(1 for br, _ in runs if br.bootstrap_completed) / n,
        perfect_rate=sum(1 for _, vr in runs if vr.all_passed) / n,
        bootstrap_md_rate=_check_rate("BOOTSTRAP.md"),
        identity_rate=_check_rate("IDENTITY.md"),
        user_rate=_check_rate("USER.md"),
        soul_rate=_check_rate("SOUL.md"),
    )


def _scrub(text: str) -> str:
    """Replace secret-looking substrings with ***."""
    return _SECRET_PATTERNS.sub(lambda m: (m.group(1) or m.group(2) or m.group(3) or "") + "***", text)


def _make_results_dir() -> Path:
    d = Path(__file__).resolve().parent.parent / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def print_summary(
    results: list[AggregatedResult],
    console: Console | None = None,
) -> None:
    """Print a rich summary table to the terminal."""
    if console is None:
        console = Console()

    table = Table(
        title="🦞 OpenClaw Bootstrapping Benchmark Results",
        show_lines=True,
    )
    table.add_column("Model", style="cyan bold")
    table.add_column("Variant", style="magenta")
    table.add_column("Runs", justify="center")
    table.add_column("Avg\nScore", justify="center")
    table.add_column("Perfect\nRate", justify="center")
    table.add_column("BOOTSTRAP.md\nDeleted", justify="center")
    table.add_column("IDENTITY.md\nPopulated", justify="center")
    table.add_column("USER.md\nPopulated", justify="center")
    table.add_column("SOUL.md\nUpdated", justify="center")
    table.add_column("Avg\nDuration", justify="right")

    for ag in results:
        score_pct = f"{ag.avg_score:.0%}"
        score_style = (
            "green" if ag.avg_score >= 0.95
            else ("yellow" if ag.avg_score >= 0.5 else "red")
        )

        def rate_str(rate: float) -> str:
            if rate == 1.0:
                return "✅"
            elif rate == 0.0:
                return "❌"
            return f"{rate:.0%}"

        table.add_row(
            ag.model_name,
            ag.prompt_variant,
            str(ag.num_runs),
            f"[{score_style}]{score_pct}[/{score_style}]",
            rate_str(ag.perfect_rate),
            rate_str(ag.bootstrap_md_rate),
            rate_str(ag.identity_rate),
            rate_str(ag.user_rate),
            rate_str(ag.soul_rate),
            f"{ag.avg_duration_s:.1f}s",
        )

    console.print()
    console.print(table)
    console.print()

    # Overall summary
    total = len(results)
    perfect = sum(1 for ag in results if ag.perfect_rate == 1.0)
    console.print(
        Panel(
            f"[bold]{perfect}/{total}[/bold] models completed bootstrap perfectly in all runs",
            title="Summary",
            border_style="green" if perfect == total else "yellow",
        )
    )


def save_json_report(
    results: list[AggregatedResult],
    path: Path | None = None,
    openclaw_version: str = "unknown",
) -> Path:
    """Write a JSON report to disk and return the file path."""
    if path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = _make_results_dir() / f"benchmark_{ts}.json"

    report: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "openclaw_version": openclaw_version,
        "models": [],
    }

    for ag in results:
        model_entry: dict = {
            "model": ag.model_name,
            "prompt_variant": ag.prompt_variant,
            "prompt_variant_prompts": ag.prompt_variant_prompts,
            "num_runs": ag.num_runs,
            "avg_score": round(ag.avg_score, 4),
            "avg_duration_s": round(ag.avg_duration_s, 2),
            "bootstrap_rate": round(ag.bootstrap_rate, 4),
            "perfect_rate": round(ag.perfect_rate, 4),
            "per_check_rates": {
                "BOOTSTRAP.md": round(ag.bootstrap_md_rate, 4),
                "IDENTITY.md": round(ag.identity_rate, 4),
                "USER.md": round(ag.user_rate, 4),
                "SOUL.md": round(ag.soul_rate, 4),
            },
            "runs": [],
        }

        if ag.runs:
            # Build run entries from live BootstrapResult/VerificationResult
            for br, vr in ag.runs:
                run_entry = {
                    "bootstrap_completed": br.bootstrap_completed,
                    "score": vr.score,
                    "total_duration_s": br.total_duration_s,
                    "turns": [
                        {
                            "prompt": t.prompt,
                            "response": _scrub(t.response),
                            "duration_s": t.duration_s,
                            "success": t.success,
                            "error": _scrub(t.error),
                        }
                        for t in br.turns
                    ],
                    "checks": [
                        {
                            "filename": c.filename,
                            "exists": c.exists,
                            "passed": c.passed,
                            "details": _scrub(c.details),
                            "content": _scrub(c.content),
                        }
                        for c in vr.checks
                    ],
                }
                model_entry["runs"].append(run_entry)
        elif ag._raw_runs_json:
            # Carried over from a previous report (--skip-completed)
            model_entry["runs"] = ag._raw_runs_json

        report["models"].append(model_entry)

    with open(path, "w") as f:
        json.dump(report, f, indent=2)

    # Also write a copy as benchmark_latest.json (committed to the repo)
    latest_path = path.parent / "benchmark_latest.json"
    with open(latest_path, "w") as f:
        json.dump(report, f, indent=2)

    return path


# ── Markdown results table ───────────────────────────────────

def load_latest_report() -> dict | None:
    """Load ``results/benchmark_latest.json`` if it exists."""
    path = _make_results_dir() / "benchmark_latest.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load benchmark_latest.json: %s", exc)
        return None


def _ok(passed: bool) -> str:
    return "✅" if passed else "❌"


def generate_results_markdown(
    results: list[AggregatedResult],
    openclaw_version: str = "unknown",
) -> str:
    """Return a markdown table summarising the benchmark results."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Determine runs count for the header
    run_counts = {ag.num_runs for ag in results}
    runs_note = (
        f"{run_counts.pop()} runs per model"
        if len(run_counts) == 1
        else "variable runs per model"
    )

    # Check if we have multiple prompt variants
    variant_names = sorted({ag.prompt_variant for ag in results})
    has_variants = len(variant_names) > 1 or (len(variant_names) == 1 and variant_names[0] != "default")

    version_note = f" · OpenClaw **{openclaw_version}**" if openclaw_version != "unknown" else ""

    lines = [
        f"### Latest results",
        f"",
        f"> Ran on **{ts}** against a local [Ollama](https://ollama.com/) server "
        f"({runs_note}, averaged){version_note}.",
        f"",
    ]

    if has_variants:
        lines.append(
            "| Model | Variant | Runs | Avg Score | Perfect | BOOTSTRAP | IDENTITY | USER | SOUL | Avg Duration |"
        )
        lines.append(
            "|-------|---------|:----:|:---------:|:-------:|:---------:|:--------:|:----:|:----:|-------------:|"
        )
    else:
        lines.append(
            "| Model | Runs | Avg Score | Perfect | BOOTSTRAP | IDENTITY | USER | SOUL | Avg Duration |"
        )
        lines.append(
            "|-------|:----:|:---------:|:-------:|:---------:|:--------:|:----:|:----:|-------------:|"
        )

    def _rate(r: float) -> str:
        if r == 1.0:
            return "✅"
        elif r == 0.0:
            return "❌"
        return f"{r:.0%}"

    for ag in results:
        score_pct = f"{ag.avg_score:.0%}"
        dur = f"{ag.avg_duration_s:.1f}s"
        if has_variants:
            lines.append(
                f"| {ag.model_name} "
                f"| {ag.prompt_variant} "
                f"| {ag.num_runs} "
                f"| {score_pct} "
                f"| {_rate(ag.perfect_rate)} "
                f"| {_rate(ag.bootstrap_md_rate)} "
                f"| {_rate(ag.identity_rate)} "
                f"| {_rate(ag.user_rate)} "
                f"| {_rate(ag.soul_rate)} "
                f"| {dur} |"
            )
        else:
            lines.append(
                f"| {ag.model_name} "
                f"| {ag.num_runs} "
                f"| {score_pct} "
                f"| {_rate(ag.perfect_rate)} "
                f"| {_rate(ag.bootstrap_md_rate)} "
                f"| {_rate(ag.identity_rate)} "
                f"| {_rate(ag.user_rate)} "
                f"| {_rate(ag.soul_rate)} "
                f"| {dur} |"
            )

    # Legend
    total = len(results)
    perfect = sum(1 for ag in results if ag.perfect_rate == 1.0)
    lines.append("")
    lines.append(
        f"**{perfect}/{total}** models completed the bootstrap perfectly in every run."
    )
    lines.append("")
    lines.append(
        "<details><summary>Column legend</summary>"
    )
    lines.append("")
    lines.append("| Column | Meaning |")
    lines.append("|--------|---------|")
    if has_variants:
        lines.append("| **Variant** | Prompt variant: *natural-guided*, *natural-unguided*, *structured-guided*, or *structured-unguided* |")
    lines.append("| **Runs** | Number of independent runs (each from a fresh environment) |")
    lines.append("| **Avg Score** | Average percentage of checks passed across all runs |")
    lines.append("| **Perfect** | Fraction of runs where all 4 checks passed (✅ = 100%) |")
    lines.append("| **BOOTSTRAP** | Rate at which `BOOTSTRAP.md` was deleted |")
    lines.append("| **IDENTITY** | Rate at which `IDENTITY.md` has real Name, Creature, Vibe, Emoji |")
    lines.append("| **USER** | Rate at which `USER.md` has real Name, Timezone |")
    lines.append("| **SOUL** | Rate at which `SOUL.md` was personalised beyond the template |")
    lines.append("| **Avg Duration** | Average wall-clock time for the bootstrap conversation |")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


def save_results_markdown(
    results: list[AggregatedResult],
    path: Path | None = None,
    openclaw_version: str = "unknown",
) -> Path:
    """Write the markdown results table to ``results/latest.md``."""
    if path is None:
        path = _make_results_dir() / "latest.md"

    md = generate_results_markdown(results, openclaw_version=openclaw_version)
    path.write_text(md, encoding="utf-8")
    logger.info("Markdown results saved to %s", path)
    return path


def update_readme_results(
    results: list[AggregatedResult],
    readme_path: Path | None = None,
    openclaw_version: str = "unknown",
) -> bool:
    """Replace content between result markers in README.md.

    Returns True if the README was updated, False if markers were missing.
    """
    if readme_path is None:
        readme_path = Path(__file__).resolve().parent.parent / "README.md"

    if not readme_path.exists():
        logger.warning("README.md not found at %s", readme_path)
        return False

    content = readme_path.read_text(encoding="utf-8")

    if _RESULTS_START not in content or _RESULTS_END not in content:
        logger.warning(
            "README.md is missing result markers (%s … %s). "
            "Skipping auto-update.",
            _RESULTS_START,
            _RESULTS_END,
        )
        return False

    md_table = generate_results_markdown(results, openclaw_version=openclaw_version)

    # Replace everything between markers (inclusive of markers)
    pattern = re.compile(
        re.escape(_RESULTS_START) + r".*?" + re.escape(_RESULTS_END),
        flags=re.DOTALL,
    )
    new_content = pattern.sub(
        f"{_RESULTS_START}\n{md_table}\n{_RESULTS_END}",
        content,
    )

    readme_path.write_text(new_content, encoding="utf-8")
    logger.info("README.md updated with latest benchmark results")
    return True

