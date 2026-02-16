"""
Top-level benchmark runner / orchestrator.

For each model in the config:
  1. Create an isolated OPENCLAW_HOME
  2. Install openclaw (local prefix — no global npm changes)
  3. Write model-specific config
  4. Run ``openclaw onboard --non-interactive``
  5. Start the gateway
  6. Send the single-prompt bootstrap via ``openclaw agent``
  7. Verify the workspace file changes
  8. Record results + auto-update README.md
  9. Tear down

Signal handlers (SIGINT / SIGTERM) ensure cleanup even on Ctrl-C.
"""

from __future__ import annotations

import atexit
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from .bootstrap import BootstrapResult, BootstrapTurn, run_bootstrap_conversation, wait_for_gateway
from .config import BenchmarkConfig, ModelConfig, PromptVariant, load_config
from .environment import OpenClawEnvironment, warm_up_model
from .preflight import print_preflight, run_preflight
from .report import (
    AggregatedResult,
    _RESULTS_END,
    _RESULTS_START,
    aggregate_runs,
    load_latest_report,
    print_summary,
    save_json_report,
    save_results_markdown,
    update_readme_results,
)
from .verify import VerificationResult, verify_bootstrap  # noqa: F811

logger = logging.getLogger(__name__)

# ── Cleanup registry ─────────────────────────────────────────
# Active environment + gateway are registered here so the signal
# handler can tear them down if the process is interrupted.
_active_env: OpenClawEnvironment | None = None
_active_gateway: subprocess.Popen[str] | None = None
_keep_env_flag: bool = False
_openclaw_version: str = "unknown"


def _emergency_cleanup(signum: int | None = None, frame: Any = None) -> None:
    """Kill the gateway and remove the temp dir on unexpected exit."""
    global _active_gateway, _active_env
    if _active_gateway is not None:
        try:
            OpenClawEnvironment.stop_gateway(_active_gateway)
        except Exception:
            pass
        _active_gateway = None
    if _active_env is not None and not _keep_env_flag:
        try:
            _active_env.cleanup()
        except Exception:
            pass
        _active_env = None
    if signum is not None:
        sys.exit(128 + signum)


# Register both SIGINT and SIGTERM
signal.signal(signal.SIGINT, _emergency_cleanup)
signal.signal(signal.SIGTERM, _emergency_cleanup)
atexit.register(_emergency_cleanup)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def run_single_model(
    cfg: BenchmarkConfig,
    model: ModelConfig,
    *,
    variant: PromptVariant | None = None,
    skip_install: bool = False,
    keep_env: bool = False,
) -> tuple[BootstrapResult, VerificationResult]:
    """Run the full benchmark pipeline for a single model."""
    global _active_env, _active_gateway, _keep_env_flag
    _keep_env_flag = keep_env

    console = Console()
    console.rule(f"[bold cyan]Model: {model.name}[/bold cyan]")

    env = OpenClawEnvironment(cfg, model)
    _active_env = env
    gateway_proc: subprocess.Popen[str] | None = None

    try:
        # 1. Install openclaw
        if not skip_install:
            console.print("[dim]Installing openclaw@latest …[/dim]")
            env.install_openclaw()
        else:
            console.print("[dim]Skipping install (--skip-install)[/dim]")

        # Detect version (used by the report)
        detected = env.detect_openclaw_version()
        global _openclaw_version
        if detected != "unknown":
            _openclaw_version = detected

        # 2. Write config
        console.print("[dim]Writing config …[/dim]")
        env.write_config()

        # 3. Run onboarding
        console.print("[dim]Running non-interactive onboarding …[/dim]")
        onboard_result = env.run_onboard()
        if onboard_result.returncode != 0:
            console.print(f"[red]Onboarding failed (exit {onboard_result.returncode})[/red]")
            console.print(f"[dim]{onboard_result.stderr[:500]}[/dim]")
            return (
                BootstrapResult(model_name=model.model_id, error="Onboarding failed"),
                VerificationResult(model_name=model.model_id),
            )

        # 4. Start gateway
        console.print("[dim]Starting gateway …[/dim]")
        gateway_proc = env.start_gateway()
        _active_gateway = gateway_proc
        time.sleep(3)  # give it a moment to bind

        if not wait_for_gateway(env, timeout=30):
            console.print("[red]Gateway did not start in time[/red]")
            # Try to proceed anyway with --local mode
            console.print("[yellow]Proceeding with --local agent mode …[/yellow]")

        # 5. Run bootstrap conversation
        console.print("[bold]Running bootstrap conversation …[/bold]")
        bootstrap_result = run_bootstrap_conversation(env, cfg, variant=variant)

        # 6. Verify
        console.print("[dim]Verifying workspace files …[/dim]")
        verification = verify_bootstrap(env.workspace_dir, model.model_id)

        console.print(f"\n[bold]{verification.summary}[/bold]\n")
        return bootstrap_result, verification

    except Exception as exc:
        logger.exception("Unexpected error for model %s", model.model_id)
        return (
            BootstrapResult(model_name=model.model_id, error=str(exc)),
            VerificationResult(model_name=model.model_id),
        )
    finally:
        # Teardown + deregister from cleanup registry
        if gateway_proc is not None:
            env.stop_gateway(gateway_proc)
        _active_gateway = None
        if not keep_env:
            env.cleanup()
        else:
            console.print(f"[dim]Keeping environment at {env.home_dir}[/dim]")
        _active_env = None


def run_benchmark(
    config_path: str | None = None,
    *,
    models: list[str] | None = None,
    skip_install: bool = False,
    skip_preflight: bool = False,
    keep_env: bool = False,
    verbose: bool = False,
    runs_per_model: int | None = None,
    skip_completed: bool = False,
) -> list[AggregatedResult]:
    """Run the full benchmark suite.

    Each model is run *runs_per_model* times from scratch (fresh
    environment each time).  The final score is the **average**
    across all runs.
    """
    _setup_logging(verbose)
    console = Console()

    cfg = load_config(config_path)

    # CLI --runs overrides config
    if runs_per_model is not None:
        cfg.runs_per_model = runs_per_model

    if not cfg.models:
        console.print("[red]No models configured in config.yaml[/red]")
        sys.exit(1)

    # Filter models if specific ones requested
    if models:
        model_set = set(models)
        cfg.models = [m for m in cfg.models if m.name in model_set]
        if not cfg.models:
            console.print(f"[red]No matching models found for: {', '.join(models)}[/red]")
            sys.exit(1)

    # ── Pre-flight checks ────────────────────────────────────
    if not skip_preflight:
        preflight = run_preflight(cfg, skip_install=skip_install)
        print_preflight(preflight, console)
        if not preflight.all_passed:
            console.print(
                "[red]Aborting benchmark due to failed pre-flight checks.[/red]\n"
                "[dim]Use --skip-preflight to bypass (not recommended).[/dim]"
            )
            sys.exit(2)
    else:
        console.print("[dim]Skipping pre-flight checks (--skip-preflight)[/dim]")

    # ── Early version detection ──────────────────────────────
    # Needed *before* the model loop so --skip-completed can compare
    # the current OpenClaw version against the previous report.
    if cfg.models:
        global _openclaw_version
        early_env = OpenClawEnvironment(cfg, cfg.models[0])
        if not skip_install:
            try:
                early_env.install_openclaw()
            except Exception:
                pass  # will be retried per-model
        detected = early_env.detect_openclaw_version()
        if detected != "unknown":
            _openclaw_version = detected
            console.print(f"[dim]OpenClaw version: {_openclaw_version}[/dim]")
        early_env.cleanup()

    n_runs = max(1, cfg.runs_per_model)

    variant_names = [v.name for v in cfg.prompt_variants] or ["default"]

    # ── Skip-completed lookup ────────────────────────────────
    # Maps (model_id, variant_name) → entry dict from the latest report.
    _prev_lookup: dict[tuple[str, str], dict] = {}
    _prev_version: str = ""
    if skip_completed:
        prev_report = load_latest_report()
        if prev_report:
            _prev_version = prev_report.get("openclaw_version", "")
            for entry in prev_report.get("models", []):
                key = (entry.get("model", ""), entry.get("prompt_variant", ""))
                _prev_lookup[key] = entry
            console.print(
                f"[dim]Loaded {len(_prev_lookup)} model/variant result(s) from "
                f"benchmark_latest.json (OpenClaw {_prev_version})[/dim]"
            )
        else:
            console.print(
                "[dim]No benchmark_latest.json found — nothing to skip[/dim]"
            )

    console.print(
        f"\n[bold]🦞 OpenClaw Bootstrapping Benchmark[/bold]\n"
        f"   Models: {len(cfg.models)}\n"
        f"   Prompt variants: {', '.join(variant_names)}\n"
        f"   Runs per model per variant: {n_runs}\n"
        f"   Retries per run: {cfg.retries}\n"
    )

    aggregated: list[AggregatedResult] = []

    for model in cfg.models:
        # Warm up: send a tiny request to force the provider to load
        # the model into memory and verify the API is reachable.
        console.print(
            f"\n[dim]Warming up {model.model_id} …[/dim]"
        )
        if warm_up_model(model):
            console.print(f"[green]✓[/green] [dim]{model.model_id} is loaded and responding[/dim]")
        else:
            console.print(
                f"[yellow]⚠ Warm-up failed for {model.model_id} — "
                f"the model may not be available. Proceeding anyway.[/yellow]"
            )

        for variant in (cfg.prompt_variants or [PromptVariant(name="default", prompts=cfg.bootstrap_prompts)]):
            # ── Skip-completed check ─────────────────────────
            if skip_completed:
                prev_key = (model.model_id, variant.name)
                prev_entry = _prev_lookup.get(prev_key)
                if prev_entry is not None:
                    prev_prompts = prev_entry.get("prompt_variant_prompts", [])
                    version_match = (_prev_version == _openclaw_version)
                    prompts_match = (prev_prompts == variant.prompts)

                    if version_match and prompts_match:
                        console.print(
                            f"\n[green]⏭  Skipping {model.model_id} / {variant.name} "
                            f"— already in latest results (same version + prompts)[/green]"
                        )
                        # Carry over the previous AggregatedResult
                        ag = AggregatedResult(
                            model_name=prev_entry["model"],
                            runs=[],  # raw runs not reconstructed
                            prompt_variant=prev_entry["prompt_variant"],
                            prompt_variant_prompts=prev_entry.get("prompt_variant_prompts", []),
                            _raw_runs_json=prev_entry.get("runs", []),
                            num_runs=prev_entry.get("num_runs", 0),
                            avg_score=prev_entry.get("avg_score", 0.0),
                            avg_duration_s=prev_entry.get("avg_duration_s", 0.0),
                            bootstrap_rate=prev_entry.get("bootstrap_rate", 0.0),
                            perfect_rate=prev_entry.get("perfect_rate", 0.0),
                            bootstrap_md_rate=prev_entry.get("per_check_rates", {}).get("BOOTSTRAP.md", 0.0),
                            identity_rate=prev_entry.get("per_check_rates", {}).get("IDENTITY.md", 0.0),
                            user_rate=prev_entry.get("per_check_rates", {}).get("USER.md", 0.0),
                            soul_rate=prev_entry.get("per_check_rates", {}).get("SOUL.md", 0.0),
                        )
                        aggregated.append(ag)
                        continue
                    else:
                        # Mismatch — warn but re-run
                        reasons = []
                        if not version_match:
                            reasons.append(
                                f"OpenClaw version changed: "
                                f"{_prev_version!r} → {_openclaw_version!r}"
                            )
                        if not prompts_match:
                            reasons.append("prompt text changed")
                        console.print(
                            f"\n[yellow]⚠  {model.model_id} / {variant.name} exists "
                            f"in latest results but {' and '.join(reasons)} — "
                            f"re-running[/yellow]"
                        )

            model_runs: list[tuple[BootstrapResult, VerificationResult]] = []

            for run_idx in range(1, n_runs + 1):
                console.rule(
                    f"[bold cyan]{model.name}[/bold cyan]  "
                    f"[dim]{variant.name} — run {run_idx}/{n_runs}[/dim]"
                )

                result: tuple[BootstrapResult, VerificationResult] | None = None

                for attempt in range(1, cfg.retries + 1 + 1):  # +1 for initial attempt
                    if attempt > 1:
                        console.print(
                            f"[yellow]Retry {attempt - 1}/{cfg.retries} for "
                            f"{model.name} ({variant.name}, run {run_idx})[/yellow]"
                        )

                    br, vr = run_single_model(
                        cfg, model,
                        variant=variant,
                        skip_install=skip_install,
                        keep_env=keep_env,
                    )

                    # Only retry on infrastructure failures:
                    #   - br.error is set (install / onboard / exception)
                    #   - a turn failed (timeout, connection error, etc.)
                    # If the model responded normally but didn't do the
                    # bootstrap correctly, that's a legitimate data point
                    # — not something to retry.
                    infra_failure = bool(br.error) or any(
                        not t.success for t in br.turns
                    )

                    result = (br, vr)

                    if not infra_failure:
                        break  # Model responded — accept the result

                    if attempt <= cfg.retries:
                        console.print(
                            f"[dim]Infrastructure issue detected — will retry …[/dim]\n"
                        )
                    else:
                        console.print(
                            f"[yellow]All retries exhausted — keeping last result[/yellow]"
                        )

                assert result is not None
                model_runs.append(result)
                console.print(
                    f"[dim]Run {run_idx} score: {result[1].score:.0%}[/dim]"
                )

            aggregated.append(aggregate_runs(
                model.model_id, model_runs,
                prompt_variant=variant.name,
                prompt_variant_prompts=variant.prompts,
            ))

    # Print summary and save report
    print_summary(aggregated, console)
    report_path = save_json_report(aggregated, openclaw_version=_openclaw_version)
    console.print(f"[dim]Full report saved to {report_path}[/dim]")

    # Generate markdown table and auto-update README
    md_path = save_results_markdown(aggregated, openclaw_version=_openclaw_version)
    console.print(f"[dim]Markdown table saved to {md_path}[/dim]")

    if update_readme_results(aggregated, openclaw_version=_openclaw_version):
        console.print("[green]✅ README.md updated with latest results[/green]\n")
    else:
        console.print(
            "[yellow]README.md was not updated — add result markers to enable auto-update.[/yellow]\n"
            "[dim]Add these lines to README.md where you want the table:[/dim]\n"
            f"[dim]  {_RESULTS_START}[/dim]\n"
            f"[dim]  {_RESULTS_END}[/dim]\n"
        )

    return aggregated
