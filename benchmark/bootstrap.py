"""
Bootstrap conversation driver.

After onboarding completes and the gateway is running, the agent's
workspace contains BOOTSTRAP.md which instructs the AI to run a
first-run identity ritual.  This module sends the bootstrap prompt(s)
from config.yaml to the agent via ``openclaw agent`` and waits for
completion.

By default the benchmark uses a **single prompt** that provides all
required information at once (user name, timezone, agent identity,
etc.) and expects the model to complete the ritual autonomously.

The bootstrap is considered successful when:
  - IDENTITY.md has real values (name, creature, vibe, emoji)
  - USER.md has real values (name, timezone)
  - SOUL.md has been updated beyond the template
  - BOOTSTRAP.md has been deleted

We use ``openclaw agent --message ...`` to drive the conversation,
which goes through the gateway and hits the model.  This avoids
fragile TUI automation (pexpect) and uses the official CLI surface.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import BenchmarkConfig, PromptVariant
from .environment import OpenClawEnvironment

logger = logging.getLogger(__name__)


@dataclass
class BootstrapTurn:
    """Record of a single bootstrap conversation turn."""

    prompt: str
    response: str = ""
    duration_s: float = 0.0
    success: bool = False
    error: str = ""


@dataclass
class BootstrapResult:
    """Outcome of the full bootstrap conversation."""

    model_name: str
    turns: list[BootstrapTurn] = field(default_factory=list)
    total_duration_s: float = 0.0
    bootstrap_completed: bool = False
    error: str = ""


def wait_for_gateway(env: OpenClawEnvironment, timeout: int = 30) -> bool:
    """Poll until the gateway is reachable or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "status"],
                env=env.env(),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Gateway is ready")
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
        time.sleep(1)
    logger.error("Gateway did not become ready within %ds", timeout)
    return False


def send_agent_message(
    env: OpenClawEnvironment,
    message: str,
    timeout: int = 120,
) -> tuple[str, float]:
    """Send a single message via ``openclaw agent`` and return (response, duration)."""
    cmd = [
        "openclaw", "agent",
        "--agent", "main",
        "--message", message,
        "--local",
        "--timeout", str(timeout),
    ]
    logger.info("Sending: %s", message[:80])
    t0 = time.time()
    result = subprocess.run(
        cmd,
        env=env.env(),
        capture_output=True,
        text=True,
        timeout=timeout + 30,  # extra buffer
    )
    duration = time.time() - t0
    response = result.stdout.strip()
    if result.returncode != 0:
        err = result.stderr.strip()
        logger.warning("Agent turn failed (exit %d): %s", result.returncode, err)
        return f"[ERROR] {err}", duration
    logger.info("Got response (%0.1fs, %d chars)", duration, len(response))
    return response, duration


def run_bootstrap_conversation(
    env: OpenClawEnvironment,
    cfg: BenchmarkConfig,
    variant: PromptVariant | None = None,
) -> BootstrapResult:
    """Drive the full bootstrap Q&A using fixed prompts.

    If *variant* is given, its prompts are used instead of the first
    configured variant.
    """
    prompts = variant.prompts if variant else cfg.bootstrap_prompts
    result = BootstrapResult(model_name=env.model.model_id)
    t0 = time.time()

    for i, prompt in enumerate(prompts, 1):
        logger.info("── Turn %d / %d ──", i, len(prompts))
        turn = BootstrapTurn(prompt=prompt)

        remaining = cfg.bootstrap_timeout - (time.time() - t0)
        if remaining <= 0:
            turn.error = "Global bootstrap timeout exceeded"
            result.turns.append(turn)
            result.error = turn.error
            break

        turn_timeout = min(cfg.agent_turn_timeout, int(remaining))

        try:
            response, dur = send_agent_message(env, prompt, timeout=turn_timeout)
            turn.response = response
            turn.duration_s = dur
            turn.success = not response.startswith("[ERROR]")
            if not turn.success:
                turn.error = response
        except subprocess.TimeoutExpired:
            turn.error = f"Turn timed out after {turn_timeout}s"
            turn.success = False
        except Exception as exc:
            turn.error = str(exc)
            turn.success = False

        result.turns.append(turn)

        if not turn.success:
            logger.warning("Turn %d failed: %s", i, turn.error)
            # Continue anyway — later prompts may still work

    result.total_duration_s = time.time() - t0

    # Check if BOOTSTRAP.md was deleted (the completion signal)
    bootstrap_path = env.workspace_dir / "BOOTSTRAP.md"
    result.bootstrap_completed = not bootstrap_path.exists()

    if result.bootstrap_completed:
        logger.info("✅ BOOTSTRAP.md was deleted — bootstrap completed!")
    else:
        logger.warning("❌ BOOTSTRAP.md still exists — bootstrap did NOT complete")

    return result
